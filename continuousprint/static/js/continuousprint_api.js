// This is an INTERNAL implementation, not to be used for any external integrations with the continuous print plugin.
// If you see something here you want, open a FR to expose it: https://github.com/smartin015/continuousprint/issues
class CPAPI {
  BASE = "plugin/continuousprint"
  JOB = "job"
  SET = "set"
  STATE = "state"
  QUEUES = "queues"
  HISTORY = "history"
  AUTOMATION = "automation"

  init(loading_vm, err_cb) {
    this.loading = loading_vm;
    this.default_err_cb = err_cb;
  }

  _call_base(url, data, cb, err_cb=undefined, blocking=true) {
    let self = this;
    if (blocking) {
      if (self.loading()) {
        console.log(`Skipping blocking call to ${url}; another call in progress`);
        return;
      }
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
        },
        error: (xhr,  textstatus, errThrown) => {
          if (blocking) {
            self.loading(false);
          }
          if (err_cb) {
            err_cb(xhr.status, errThrown);
          } else {
            self.default_err_cb(xhr.status, errThrown);
          }
        }
    });
  }

  _call(type, method, data, cb, err_cb=undefined, blocking=true) {
    return this._call_base(`${this.BASE}/${type}/${method}`, data, cb, err_cb, blocking);
  }

  get(type, cb, err_cb=undefined) {
    // History/scripts fetching doesn't mess with mutability
    let blocking = (type !== this.HISTORY && type !== this.AUTOMATION);
    this._call(type, 'get', undefined, cb, err_cb, blocking);
  }

  add(type, data, cb) {
    data = {json: JSON.stringify(data)};
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

  getSpoolManagerState(cb, err_cb) {
    this._call_base("plugin/SpoolManager/loadSpoolsByQuery?from=0&to=1000000&sortColumn=displayName&sortOrder=desc&filterName=&materialFilter=all&vendorFilter=all&colorFilter=all", undefined, cb, err_cb, false);
  }

  setActive(active, cb) {
    this._call_base(`${this.BASE}/set_active`, {active}, cb);
  }

  simulate(automation, symtable, cb, err_cb) {
    this._call(this.AUTOMATION, 'simulate', {symtable: JSON.stringify(symtable), automation: JSON.stringify(automation)}, cb, err_cb, false);
  }
}

try {
  module.exports = CPAPI;
} catch {}
