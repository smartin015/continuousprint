// This is an INTERNAL implementation, not to be used for any external integrations with the continuous print plugin.
// If you see something here you want, open a FR to expose it: https://github.com/smartin015/continuousprint/issues
class CPAPI {
  BASE = "plugin/continuousprint"
  SET = "set"
  JOB = "job"

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
    this._call(`${this.BASE}/state`, undefined, cb);
  }

  add(type, data, cb) {
    this._call(`${this.BASE}/${type}/add`, data, cb);
  }

  update(type, data, cb) {
    this._call(`${this.BASE}/${type}/update`, data, cb);
  }

  mv(type, data, cb) {
    this._call(`${this.BASE}/${type}/mv`, data, cb);
  }

  rm(data, cb) {
    this._call(`${this.BASE}/multi/rm`, data, cb);
  }

  reset(data, cb) {
    this._call(`${this.BASE}/multi/reset`, data, cb);
  }

  setActive(active, cb) {
    this._call(`${this.BASE}/set_active`, {active}, cb);
  }

  history(cb) {
    this._call(`${this.BASE}/history`, undefined, cb, false);
  }

  clearHistory(cb) {
    this._call(`${this.BASE}/clearHistory`, {}, cb, false);
  }

  queues(cb) {
    this._call(`${this.BASE}/queues`, undefined, cb, false);
  }

  commitQueues(data, cb) {
    this._call(`${this.BASE}/queues/commit`, data, cb);
  }

  getSpoolManagerState(cb) {
    this._call("plugin/SpoolManager/loadSpoolsByQuery?from=0&to=1000000&sortColumn=displayName&sortOrder=desc&filterName=&materialFilter=all&vendorFilter=all&colorFilter=all", undefined, cb, false);
  }
}

try {
  module.exports = CPAPI;
} catch {}
