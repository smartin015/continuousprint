/*
 * View model for OctoPrint-Print-Queue
 *
 * Author: Michael New
 * License: AGPLv3
 */

$(function() {
	function ContinuousPrintViewModel(parameters) {
		var self = this;
		self.params = parameters;

		self.printerState = parameters[0];
		self.loginState = parameters[1];
		self.files = parameters[2];
		self.settings = parameters[3];


		self.onBeforeBinding = function() {
			self.loadQueue();
		}
		
		self.loadQueue = function() {
			$('#queue_list').html("");
			$.ajax({
				url: "plugin/continuousprint/queue",
				type: "GET",
				dataType: "json",
				headers: {
					"X-Api-Key":UI_API_KEY,
				},
				success:function(r){
					if (r.queue.length > 0) {
						for(var i = 0; i < r.queue.length; i++) {
							var file = r.queue[i];
							var row = $("<div style='padding: 10px;border-bottom: 1px solid #000;"+(i==0 ? "background: #c2fccf;" : "")+"'>"+file.name+"<div class='pull-right'><i style='cursor: pointer' class='fa fa-minus text-error' data-index='"+i+"'></i></div></div>");
							row.find(".fa").click(function() {
								self.removeFromQueue($(this).data("index"));
							});
							$('#queue_list').append(row);
						}
					} else {
						$('#queue_list').html("<div style='text-align: center'>Queue is empty</div>");
					}
				}
			});
		}
			
		

		$(document).ready(function(){
			$('#file_list').html("");
			$.ajax({
				url: "/api/files?recursive=true",
				type: "GET",
				dataType: "json",
				headers: {
					"X-Api-Key":UI_API_KEY,
				},
				success:function(r){
					if (r.files.length > 0) {
						for(var i = 0; i < r.files.length; i++) {
							var file = r.files[i];
							if (file.name.toLowerCase().indexOf(".gco") > -1 || file.name.toLowerCase().indexof(".gcode") > -1) {
								var row = $("<div style='padding: 10px;border-bottom: 1px solid #000;'>"+file.name+"<div class='pull-right'><i style='cursor: pointer' class='fa fa-plus text-success' data-name='"+file.name+"' data-path='"+file.path+"' data-sd='"+(file.origin=="local" ? false : true)+"'></i></div></div>");
								row.find(".fa").click(function() {
									self.addToQueue({
										name: $(this).data("name"),
										path: $(this).data("path"),
										sd: $(this).data("sd")
									});
								});
								$('#file_list').append(row);
							}
						}
					} else {
						$('#file_list').html("<div style='text-align: center'>No files found</div>");
					}
				}
			});
		});

		self.addToQueue = function(data) {
			$.ajax({
				url: "plugin/continuousprint/addqueue",
				type: "POST",
				dataType: "text",
				headers: {
					"X-Api-Key":UI_API_KEY,
				},
				data: data,
				success: function(c) {
					self.loadQueue();
				},
				error: function() {
					self.loadQueue();
				}
			});
		}
		
		self.removeFromQueue = function(data) {
			$.ajax({
				url: "plugin/continuousprint/removequeue?index=" + data,
				type: "DELETE",
				dataType: "text",
				headers: {
					"X-Api-Key":UI_API_KEY,
				},
				success: function(c) {
					self.loadQueue();
				},
				error: function() {
					self.loadQueue();
				}
			});
		}

		self.startQueue = function() {
			$.ajax({
				url: "plugin/continuousprint/startqueue",
				type: "GET",
				dataType: "json",
				headers: {
					"X-Api-Key":UI_API_KEY,
				},
				data: {}
			});
		}

		self.onDataUpdaterPluginMessage = function(plugin, data) {
			if (plugin != "continuousprint") return;

			switch(data["type"]) {
				case "popup":
					new PNotify({
						title: 'Continuous Print',
						text: data.msg,
						type: 'info',
						hide: true,
						buttons: {
							closer: true,
							sticker: false
						}
					});
					break;
				case "complete":
					new PNotify({
						title: 'Continuous Print',
						text: data.msg,
						type: 'success',
						hide: true,
						buttons: {
							closer: true,
							sticker: false
						}
					});
					self.loadQueue();
					break;
				case "reload":
					if (data.msg != "") {
						new PNotify({
							title: 'Continuous Print',
							text: data.msg,
							type: 'success',
							hide: true,
							buttons: {
								closer: true,
								sticker: false
							}
						});
					}
					self.loadQueue();
					break;
			}
		}
	}

	// This is how our plugin registers itself with the application, by adding some configuration
	// information to the global variable OCTOPRINT_VIEWMODELS
	OCTOPRINT_VIEWMODELS.push([
		// This is the constructor to call for instantiating the plugin
		ContinuousPrintViewModel,

		// This is a list of dependencies to inject into the plugin, the order which you request
		// here is the order in which the dependencies will be injected into your view model upon
		// instantiation via the parameters argument
		["printerStateViewModel", "loginStateViewModel", "filesViewModel", "settingsViewModel"],

		// Finally, this is the list of selectors for all elements we want this view model to be bound to.
		["#tab_plugin_continuousprint"]
	]);
});
