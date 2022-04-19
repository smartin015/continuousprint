// This is an INTERNAL implementation, not to be used for any external integrations with the continuous print plugin.
// If you see something here you want, open a FR to expose it: https://github.com/smartin015/continuousprint/issues
class CPAPI {
  BASE = "plugin/continuousprint/"

  _call(url, cb, type, data) {
    $.ajax({
        url: url,
        type: type || "GET",
        dataType: "json",
        data: data,
        headers: {"X-Api-Key":UI_API_KEY},
        success:cb
    });
  }

  getState(cb) {
    this._call(this.BASE + "state", cb);
  }

  assign(items, cb) {
    this._call(this.BASE + "assign", cb, "POST", {items: JSON.stringify(items)});
  }

  setActive(active, cb) {
    this._call(this.BASE + "set_active", cb, "POST", {active});
  }

  getSpoolManagerState(cb) {
    this._call("plugin/SpoolManager/loadSpoolsByQuery?selectedPageSize=25&from=0&to=25&sortColumn=displayName&sortOrder=desc&filterName=&materialFilter=all&vendorFilter=all&colorFilter=all", cb, "GET");
  }
}

try {
  module.exports = CPAPI;
} catch {}
