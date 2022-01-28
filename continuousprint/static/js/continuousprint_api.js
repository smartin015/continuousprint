

class CPrintAPI {
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

  getFileList(cb) {
    this._call("/api/files?recursive=true", cb);
  }

  add(items, idx, cb) {
    this._call(this.BASE + "add", cb, "POST", {items: JSON.stringify(items), idx});
  }

  assign(items, cb) {
    this._call(this.BASE + "assign", cb, "POST", {items: JSON.stringify(items)});
  }

  remove(idx, count, cb) {
    console.log("remove idx", idx, "count", count);
    this._call(this.BASE + "remove", cb, "POST", {idx, count});
  }

  move(idx, count, offs, cb) {
    console.log("move idx", idx, "count", count, "offs", offs);
    this._call(this.BASE + "move", cb, "POST", {idx, count, offs});
  }

  setActive(active, cb) {
    this._call(this.BASE + "set_active", cb, "POST", {active});
  }

  clear(cb, keep_failures, keep_non_ended) {
    this._call(this.BASE + "clear", cb, "POST", {keep_failures, keep_non_ended});
  }
}
