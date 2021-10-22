/*
 * View model for OctoPrint-Print-Queue
 *
 * Contributors: Michael New, Scott Martin
 * License: AGPLv3
 */

$(function() {

    const QueueState = {
      UNKNOWN: null,
      QUEUED: "queued",
      PRINTING: "printing",
      
    }

    // see QueueItem in print_queue.py for matching python object
    function QueueItem(data) {
      var self = this;
      self.name = data.name;
      self.path = data.path;
      self.sd = data.sd;
      self.start_ts = ko.observable(data.start_ts);
      self.end_ts = ko.observable(data.end_ts);
      self.result = ko.observable(data.result);
    }

    function QueueSetItem(items, idx) {
      var self = this;
      self.idx = idx;
      self._n = items[0].name; // Used for easier inspection in console
      self._len = items.length;
      self.items = ko.observableArray(items);
      self.length = ko.computed(function() {return self.items().length;});
      self.name = ko.computed(function() {return self.items()[0].name;});
      self.path = ko.computed(function() {return self.items()[0].path;});
      self.sd = ko.computed(function() {return self.items()[0].sd;});
      self.start_ts = ko.computed(function() {return self.items()[0].start_ts;});
      self.end_ts = ko.computed(function() {
        for (let item of self.items()) {
          if (item.end_ts !== null) {
            return item.end_ts();
          }
        }
        return null;
      });
      self.result = ko.computed(function() {
        return self.items()[self.items().length-1].result;
      })
      self.num_completed = ko.computed(function() {
        let i = 0;
        for (let item of self.items()) {
          if (item.end_ts() !== null) {
            i++;
          }
        }
        return i;
      })
    }

    function ContinuousPrintViewModel(parameters) {
        var self = this;
        self.api = new CPrintAPI();

        // These are used in the jinja template (TODO CONFIRM)
        self.printerState = parameters[0];
        self.loginState = parameters[1];
        self.is_paused = ko.observable(false);
        self.is_looped = ko.observable();
        self.searchtext = ko.observable("");
        self.queue = ko.observableArray([]);
        self.queuesets = ko.computed(function() {
          let result = [];
          let cur = [];
          let curName = null;
          let q = self.queue();
          let i = 0;
          let qidx = 0;
          for (; i < q.length; i++) {
            let item = q[i];
            if (curName !== item.name) {
              if (curName !== null) {
                result.push(new QueueSetItem(cur, qidx));
              }
              qidx = i;
              cur = [];
              curName = item.name;
            }
            cur.push(item);
          }
          if (cur.length) {
            result.push(new QueueSetItem(cur, qidx));
          }
          console.log(result);
          return result;
        });
        self.filelist = ko.observableArray([]);
        
        self.onBeforeBinding = function() {
            self._loadState();
            self._getFileList();
        }
  
        // Patch the files panel to allow for adding to queue
        self.files = parameters[2];
        self.files.add = function(data) {
            self.api.add([{
                name:data.name,
                path:data.path,
                sd: (data.origin !== "local"),
              }], undefined, self._setState);
        };

        self._loadState = function(state) {
            self.api.getState(self._setState);
        };    
        self._setState = function(state) {
            self.queue($.map(state.queue, function(i) {
              return new QueueItem(i);
            }));
            self.is_looped(state.looped);
        }
                        
        self._getFileList = function() {
            self.api.getFileList(function(r){
                self.filelist(self._unrollFilesRecursive(r.files));
            });
        }
        self._unrollFilesRecursive = function(files) {
            var result = [];
            for(var i = 0; i < files.length; i++) {
                var file = files[i];
                // Matches *.gco, *.gcode
                if (file.name.toLowerCase().indexOf(".gco") > -1) {
                    result.push(file);
                } else if (file.children !== undefined) {
                    result = result.concat(self._unrollFilesRecursive(file.children));
                }
            }
            return result;
        }

        // *** ko template methods ***
        self.startQueue = function(clearHistory) {
          console.log("starting queue");
            self.api.start(clearHistory, () => {
                self.is_paused(false);
            });
        }
        self.setLoop = function(loop) {
            self.api.setLoop((r) => {
              self.is_looped(r === "true");
            });
        }

        self.countKeypress = function(cnt, key) {

          if (key.keyCode == 13) {
            self.changeCount(cnt);
          }
        }
        self.setCount = function(cnt, e) {
          console.log("TODO validate change");
          let diff =  parseInt(e.target.value, 10) - cnt.length();
          if (diff > 0) {
            let items = [];
            for (let i = 0; i < diff; i++) {
              items.push(new QueueItem({"name": cnt.name(), "path": cnt.path(), "sd": cnt.sd()}));
            }
            self.api.add(items, cnt.idx + cnt.length(), self._setState);
          } else if (diff < 0) {
            self.api.remove(cnt.idx + (cnt.length() + diff - 1), -diff, self._setState);
          } 
          // Do nothing if equal
        }

        self.move = function(queueset, queueset_offs) {
            let qss = self.queuesets();
            let src = qss.indexOf(queueset);
            if (src === -1) {
              throw Error("Unknown queueset item: " + item); 
            }
            if (queueset_offs != 1 && queueset_offs != -1) {
              throw Error("Only single digit shifts allowed");
            }
            // Compute absolute offset (flattening all queue sets)
            let t_idx = qss[src+queueset_offs].idx;
            let s_idx = queueset.idx;
            let abs_offs = (t_idx < s_idx) ? t_idx - s_idx : qss[src+queueset_offs].length();
            self.api.move(queueset.idx, queueset.length(), abs_offs, self._setState);
        }
        self.remove = function(queueset) {
            self.api.remove(queueset.idx, queueset.length(), self._setState);
        }
        self.add = function(data) {
            let item = {
                name:data.name,
                path:data.path,
                sd: (data.origin !== "local"),
            };
            self.api.add([item], undefined, self._setState);
        }
        // ***

        self.onDataUpdaterPluginMessage = function(plugin, data) {
            if (plugin != "continuousprint") return;
            var theme;
            switch(data["type"]) {
                case "popup":
                    theme = "info";
                    break;
                case "error":
                    theme = 'danger';
                    self._loadState();
                    break;
                case "complete":
                    theme = 'success';
                    self._loadState();
                    break;
                case "reload":
                    theme = 'success'
                    self._loadState();
                    break;
                case "paused":
                    self.is_paused(true);
                    break;
                case "updatefiles":
                    self.getFileList();
                    break;
                default:
                    theme = "info";
                    break;
            }
            
            if (data.msg != "") {
                new PNotify({
                    title: 'Continuous Print',
                    text: data.msg,
                    type: theme,
                    hide: true,
                    buttons: {closer: true, sticker: false}
                });
            }
        }
    }
    /**/

    $(document).ready(function(){
        /*
         * This adds a "Q" button to the left file panel for quick access
         * Adapted from OctoPrint-PrusaSlicerThumbnails
         * https://github.com/jneilliii/OctoPrint-PrusaSlicerThumbnails/blob/master/octoprint_prusaslicerthumbnails/static/js/prusaslicerthumbnails.js
         */
        let regex = /<div class="btn-group action-buttons">([\s\S]*)<.div>/mi;
        let template = '<div class="btn btn-mini bold" data-bind="click: function() { if ($root.loginState.isUser()) { $root.add($data) } else { return; } }" title="Add To Queue" ><i></i>Q</div>';

        $("#files_template_machinecode").text(function () {
            var return_value = $(this).text();
            return_value = return_value.replace(regex, '<div class="btn-group action-buttons">$1    ' + template + '></div>');
            return return_value
        });
    });


    // Add config info to the global var to register our plugin
    OCTOPRINT_VIEWMODELS.push([
        // This is the constructor to call for instantiating the plugin
        ContinuousPrintViewModel,

        // Dependencies (injected in-order)
        [
          "printerStateViewModel", 
          "loginStateViewModel",
          "filesViewModel", 
          "settingsViewModel"
        ],

        // Selectors for all elements binding to this view model
        ["#tab_plugin_continuousprint"]
    ]);
});
