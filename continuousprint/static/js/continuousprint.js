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

		// https://stackoverflow.com/questions/6108819/javascript-timestamp-to-relative-time
		function timeAgo(previous, current = new Date()) {
				var msPerHour = 60 * 60 * 1000;
				var msPerDay = msPerHour * 24;
				var msPerMonth = msPerDay * 30;
				var elapsed = current - previous;
				if (elapsed < msPerHour) {
						 return Math.round(elapsed/msPerMinute) + ' minutes';   
				}
				else if (elapsed < msPerDay ) {
						 return Math.round(elapsed/msPerHour) + ' hours';   
				}
				else if (elapsed < msPerMonth) {
						return Math.round(elapsed/msPerDay) + ' days';   
				}
				else {
						return Math.round(elapsed/msPerMonth) + ' months';   
				}
		}

    // see QueueItem in print_queue.py for matching python object
    function QueueItem(data, idx) {
      var self = this;
      self.idx = idx;
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
      self.start_ts = ko.computed(function() {return self.items()[0].start_ts();});
      self.end_ts = ko.computed(function() {
        for (let item of self.items()) {
          if (item.end_ts !== null) {
            return item.end_ts();
          }
        }
        return null;
      });
      self.result = ko.computed(function() {
        return self.items()[self.items().length-1].result();
      })
      self.num_completed = ko.computed(function() {
        let i = 0;
        for (let item of self.items()) {
          if (item.end_ts() !== null) {
            i++;
          }
        }
        return i;
      });
      self.progress = ko.computed(function() {
				return (self.num_completed() / self.length()).toFixed(0) + "%";
      });
      self.description = ko.computed(function() {
        if (self.start_ts() === null) {
          return "Pending";
        } else if (self.active()) {
          return `Started ${timeAgo(self.start_ts)} ago`;
        } else if (self.end_ts !== null) {
					return `${self.result} (${timeAgo(self.end_ts)} ago; took ${timeAgo(self.end_ts - self.start_ts)})`;
				} else {
					return self.result;
				}
      });
    }

    function ContinuousPrintViewModel(parameters) {
        var self = this;
        self.api = new CPrintAPI();

        // These are used in the jinja template (TODO CONFIRM)
        self.printerState = parameters[0];
				console.log(self.printerState);
        self.loginState = parameters[1];
        self.is_paused = ko.observable(false);
        self.is_looped = ko.observable();
        self.searchtext = ko.observable("");
        self.queue = ko.observableArray([]);
        self.selected = ko.observable(0);
        self.showFileList = ko.observable(false);
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
      	self.activeIdx = ko.computed(function() {
					if (!self.printerState.isPrinting() && !self.printerState.isPaused()) {
						return null;
					}
					let q = self.queue(); 
					let printname = self.printerState.filename();
					for (let i = 0; i < q.length; i++) {
						if (q[i].end_ts() === null && q[i].name === printname) {
							return i;
						}
					}
          console.log("No valid idx found");
          return null;
				});
        self.activeQueueSet = ko.computed(function() {
          let idx = self.activeIdx();
          console.log("Active idx ", idx);
          if (idx === null) {
            return null;
          }
          for (let qss of self.queuesets()) {
            if (idx >= qss.idx && idx < qss.idx + qss.length()) {
              console.log("Matches QSS");
              return qss.idx;
            }
          }
          return null;
        });

        
        self.onBeforeBinding = function() {
            self._loadState();
            self._getFileList();
        }
  
        // Patch the files panel to allow for adding to queue
        self.files = parameters[2];
        self.files.add = function(data) {
            self.api.add([{
                name: data.name,
                path: data.path,
                sd: (data.origin !== "local"),
              }], undefined, (state) => {
                new PNotify({
                    title: 'Continuous Print',
                    text: "Added " + data.name,
                    type: "success",
                    hide: true,
                    buttons: {closer: true, sticker: false}
                });
                self._setState(state);
              });
        };

        self._loadState = function(state) {
            self.api.getState(self._setState);
        };    
        self._setState = function(state) {
            self.queue($.map(state.queue, function(q, i) {
              return new QueueItem(q, i);
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
        self.setSelected = function(sel) {
            self.selected((sel.idx === self.selected()) ? null : sel.idx);
        }
        self.toggleFileList = function() {
            self.showFileList(!self.showFileList());
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
