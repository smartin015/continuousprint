// This is an INTERNAL implementation, not to be used for any external integrations with the continuous print plugin.
// If you see something here you want, open a FR to expose it: https://github.com/smartin015/continuousprint/issues
class CPAPI {
  BASE = "plugin/continuousprint"
  JOB = "job"
  SET = "set"
  STATE = "state"
  QUEUES = "queues"
  HISTORY = "history"

  init(loading_vm) {
    console.log("API init");
    this.loading = loading_vm;
  }

  _call_base(url, data, cb, blocking=true) {
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
          console.log("CPQ call success:", result);
          cb(result);
          if (blocking) {
            self.loading(false);
          }
        }
    });
  }

  _call(type, method, data, cb, blocking=true) {
    return this._call_base(`${this.BASE}/${type}/${method}`, data, cb, blocking);
  }

  get(type, cb) {
    // History fetching doesn't mess with mutability
    let blocking = (type !== this.HISTORY);
    this._call(type, 'get', undefined, cb, blocking);
  }

  add(type, data, cb) {
    this._call(type, 'add', data, cb);
  }

  edit(type, data, cb) {
    data = {json: JSON.stringify(data)};
    this._call(type, 'edit', data, cb);
  }

  mv(type, data, cb) {
    this._call(type, 'mv', data, cb);
  }

  rm(type, data, cb) {
    this._call(type, 'rm', data, cb);
  }

  reset(type, data, cb) {
    this._call(type, 'reset', data, cb);
  }

  submit(type, data, cb) {
    this._call(type, 'submit', data, cb);
  }

  export(type, data, cb) {
    this._call(type, 'export', data, cb);
  }

  import(type, data, cb) {
    this._call(type, 'import', data, cb);
  }

  getSpoolManagerState(cb) {
    this._call_base("plugin/SpoolManager/loadSpoolsByQuery?from=0&to=1000000&sortColumn=displayName&sortOrder=desc&filterName=&materialFilter=all&vendorFilter=all&colorFilter=all", undefined, cb, false);
  }

  setActive(active, cb) {
    this._call_base(`${this.BASE}/set_active`, {active}, cb);
  }

}

try {
  module.exports = CPAPI;
} catch {}
