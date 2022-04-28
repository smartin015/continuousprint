// This is an INTERNAL implementation, not to be used for any external integrations with the continuous print plugin.
// If you see something here you want, open a FR to expose it: https://github.com/smartin015/continuousprint/issues
class CPAPI {
  BASE = "plugin/continuousprint/"

  init(loading_vm) {
    console.log("API init");
    this.loading = loading_vm;
  }

  _call(url, data, cb, blocking=true) {
    let self = this;
    if (blocking) {
      if (self.loading()) {
        return;
      }
      console.log("set loading")
      self.loading(true);
    }
    $.ajax({
        url: url,
        type: (data !== undefined) ? "POST" : "GET",
        dataType: "json",
        data: data,
        headers: {"X-Api-Key":UI_API_KEY},
        success: (result) => {
          console.log("success", result);
          cb(result);
          if (blocking) {
            self.loading(false);
          }
        }
    });
  }

  getState(cb) {
    this._call(this.BASE + "state", undefined, cb);
  }

  addSet(data, cb) {
    this._call(this.BASE + "set/add", data, cb);
  }

  updateSet(data, cb) {
    this._call(this.BASE + "set/update", data, cb);
  }

  mvSet(data, cb) {
    this._call(this.BASE + "set/mv", data, cb);
  }

  rmSet(data, cb) {
    this._call(this.BASE + "set/rm", data, cb);
  }

  addJob(cb) {
    this._call(this.BASE + "job/add", {}, cb);
  }

  updateJob(data, cb) {
    this._call(this.BASE + "job/update", data, cb);
  }

  mvJob(data, cb) {
    this._call(this.BASE + "job/mv", data, cb);
  }

  rmJob(data, cb) {
    this._call(this.BASE + "job/rm", data, cb);
  }

  setActive(active, cb) {
    this._call(this.BASE + "set_active", {active}, cb);
  }

  getSpoolManagerState(cb) {
    this._call("plugin/SpoolManager/loadSpoolsByQuery?from=0&to=1000000&sortColumn=displayName&sortOrder=desc&filterName=&materialFilter=all&vendorFilter=all&colorFilter=all", undefined, cb, false);
  }
}

try {
  module.exports = CPAPI;
} catch {}
