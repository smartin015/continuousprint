/*
 * View model for OctoPrint-Print-Queue
 *
 * Contributors: Michael New, Scott Martin
 * License: AGPLv3
 */

$(function() {
    $(document).ready(function(){
        // This is admittedly quite gross code that uses javascript to pull text out of a script tag,
        // Format it as HTML, modify it, export it back to text, and spit it back out into the template script
        // So Bootstrap.JS can then use it to stamp out individual file entries.
        // This appears to be the most convenient option, as OctoPrint only has three file types: machinecode, model, and folder.
        // Each type has very specific behavior that we do not want for .gjob files (which are machine code, but not directly usable).
        let regex = /<div class="btn-group action-buttons">([\s\S]*)<.div>/mi;
        let titleregex = /<div class="title clickable"(.*)>([\s\S]*)<.div>/mi;
        let template = '<div class="btn btn-mini bold" data-bind="click: function() { if ($root.loginState.isUser()) { $root.add($data) } else { return; } }" title="Add To Continuous Print Queue" ><i class="fas fa-plus"></i></div>';

        let mc = $("#files_template_machinecode");
        let mctmpl = $($.parseHTML('<div>' + mc.text() + '</div>')[0]);
        let actions = mctmpl.find('.action-buttons');
        actions.attr('data-bind', "css: 'cpq-' + display.split('.')[1]");
        actions.append(template);
        let title = mctmpl.find('div.title');
        title.attr('data-bind', title.attr('data-bind').replace(", text: display", ""));
        title.append(`<i class="fas fa-archive cpq-gjob" data-bind="visible: display.endsWith('.gjob')"></i>`);
        title.append('<span data-bind="text: display"></span>');

        mc.text(mctmpl.html());

        // Also inject the add-to-queue button for models, which can be auto-sliced
        let mdl = $("#files_template_model");
        let modeltmpl = $($.parseHTML('<div>' + mdl.text() + '</div>')[0]);
        actions = modeltmpl.find('.action-buttons');
        actions.attr('data-bind', "css: 'cpq-' + display.split('.')[1]");
        actions.append(template);

        mdl.text(modeltmpl.html());

        // This injects the status of the queue into PrinterStateViewModel (the "State" panel)
        $("#state .accordion-inner").prepend(`
          <div title="Continuous Print Queue State">
            Queue:
            <span data-bind="css: continuousPrintStateStatus">
                <i data-bind="css: continuousPrintStateIcon, visible: continuousPrintStateIcon"></i>
                <strong data-bind="text: continuousPrintStateString"></strong>
            </span>
          </div>`);
    });

    OCTOPRINT_VIEWMODELS.push({
        construct: CPViewModel,
        dependencies: [
          "printerStateViewModel",
          "loginStateViewModel",
          "filesViewModel",
          "printerProfilesViewModel",
          "settingsViewModel",
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
