/*
 * View model for OctoPrint-Print-Queue
 *
 * Contributors: Michael New, Scott Martin
 * License: AGPLv3
 */

$(function() {
    function ContinuousPrintViewModel(parameters) {
        var self = this;
        self.api = new CPrintAPI();

        // These are used in the jinja template (TODO CONFIRM)
        self.printerState = parameters[0];
        self.loginState = parameters[1];
        self.is_paused = ko.observable();
        self.is_looped = ko.observable();
        self.queue = ko.observable();
        self.history = ko.observable();
        self.filelist = ko.observable();
        
        self.onBeforeBinding = function() {
            self._loadState();
            self._getFileList();
            self.is_paused(false);
        }
  
        // Patch the files panel to allow for adding to queue
        self.files = parameters[2];
        self.files.add = function(data) {
            self.api.add({
                name:data.name,
                path:data.path,
                sd: (data.origin !== "local") ? "true" : "false",
                count:1
            });
        }

        self._loadState = function(state) {
          if (state !== undefined) {
            self.api.getState(function(r) {
              self.queue(r.queue);
              self.history(r.history);
              self.is_looped(r.looped);
            });
          } else {
            self.queue(r.queue);
            self.history(r.history);
            self.is_looped(r.looped);
          }
        };    
                        
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

        // *** Jinja template methods ***
        self.startQueue = function(clearHistory) {
            self.api.start(clearHistory, () => {
                self.is_paused(false);
            });
        }
        self.setLoop = function(loop) {
            self.api.setLoop((r) => {
              self.is_looped(r === "true");
            });
        }
        self.move = function(src, dest) {
            self.api.move(src, dest, self._loadState);
        }
        self.add = function(data) {
            self.api.add({
                name:data.name,
                path:data.path,
                sd: (data.origin !== "local") ? "true" : "false",
                count:1
            }, self._loadState);
        }
        self.remove = function(idx) {
            self.api.remove(idx, self._loadState);
        }
        self.changeCount = function(idx, count) {
            self.api.changeCount(idx, count, self._loadState);
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
                    self.loadState();
                    break;
                case "complete":
                    theme = 'success';
                    self.loadState();
                    break;
                case "reload":
                    theme = 'success'
                    self.loadState();
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
        
        /*
         * This adds a "Q" button to the left file panel for quick access
         * Adapted from OctoPrint-PrusaSlicerThumbnails
         * https://github.com/jneilliii/OctoPrint-PrusaSlicerThumbnails/blob/master/octoprint_prusaslicerthumbnails/static/js/prusaslicerthumbnails.js
         */
        self.patchLeftFileBrowser = function() {
                let regex = /<div class="btn-group action-buttons">([\s\S]*)<.div>/mi;
                let template = '<div class="btn btn-mini bold" data-bind="click: function() { if ($root.loginState.isUser()) { $root.add($data) } else { return; } }" title="Add To Queue" ><i></i>Q</div>';

                $("#files_template_machinecode").text(function () {
                    var return_value = $(this).text();
                    return_value = return_value.replace(regex, '<div class="btn-group action-buttons">$1    ' + template + '></div>');
                    return return_value
                });
        }
    }
    /**/

    $(document).ready(function(){
        self.patchLeftFileBrowser();
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
