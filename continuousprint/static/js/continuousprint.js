/*
 * View model for OctoPrint-Print-Queue
 *
 * Contributors: Michael New, Scott Martin
 * License: AGPLv3
 */

$(function() {
    $(document).ready(function(){
        /*
         * This adds a button to the left file panel to add prints to the queue
         * Adapted from OctoPrint-PrusaSlicerThumbnails
         * https://github.com/jneilliii/OctoPrint-PrusaSlicerThumbnails/blob/master/octoprint_prusaslicerthumbnails/static/js/prusaslicerthumbnails.js
         */
        let regex = /<div class="btn-group action-buttons">([\s\S]*)<.div>/mi;
        let template = '<div class="btn btn-mini bold" data-bind="click: function() { if ($root.loginState.isUser()) { $root.add($data) } else { return; } }" title="Add To Continuous Print Queue" ><i class="fas fa-plus"></i></div>';

        $("#files_template_machinecode").text(function () {
            var return_value = $(this).text();
            return_value = return_value.replace(regex, '<div class="btn-group action-buttons">$1    ' + template + '></div>');
            return return_value
        });
    });

    OCTOPRINT_VIEWMODELS.push({
        construct: CPViewModel,
        dependencies: [
          "printerStateViewModel",
          "loginStateViewModel",
          "filesViewModel",
          "printerProfilesViewModel",
        ],
        elements: ["#tab_plugin_continuousprint"]
    });
    OCTOPRINT_VIEWMODELS.push({
        construct: CPSettingsViewModel,
        dependencies: [
          "settingsViewModel",
          "filesViewModel",
        ],
        elements: ["#settings_plugin_continuousprint"]
    });
});
