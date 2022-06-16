// See https://docs.octoprint.org/en/master/api/general.html#authorization for
// where to get this value
const UI_API_KEY = "YOUR_KEY_HERE";

const setActive = function(active=true, callback) {
    $.ajax({
      url: "plugin/continuousprint/set_active",
      type: "POST",
      dataType: "json",
      headers: {"X-Api-Key":UI_API_KEY},
      data: {active}
    }).done(callback);
};

const addSet = function(data, callback) {
    data = {...data, sd: false, count: 1, jobName: 'Job', jobDraft: true};
    $.ajax({
      url: "plugin/continuousprint/set/add",
      type: "POST",
      dataType: "json",
      headers: {"X-Api-Key": UI_API_KEY},
      data
    }).done(callback)

const getState = function(callback) {
    $.ajax({
      url: "plugin/continuousprint/state/get",
      type: "GET",
      dataType: "json",
      headers: {"X-Api-Key":UI_API_KEY},
    }).done(callback)
};

console.log("Stopping print queue");
setActive(false, function(data) {console.log('stopped');});

console.log("Adding new set/job");
addSet({path: "example.gcode"}, function(data) {console.log(data);});

console.log("Getting state");
getState(function(data) {console.log(data);});
