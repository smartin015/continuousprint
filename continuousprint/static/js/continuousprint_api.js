

class CPrintAPI {
  BASE = "plugin/continuousprint/"

  _simple_get(url, cb, type, data) {
    $.ajax({
        url: url,
        type: type || "GET",
        dataType: "json",
        data: data,
        headers: {"X-Api-Key":UI_API_KEY},
        success: cb,
        error: (e) => {throw new Error(e);},
    });
  }

  getState(cb) {
    this._simple_get(this.BASE + "state", cb);
  }

  getFileList(cb) {
    this._simple_get("/api/files?recursive=true", cb);
  }

  add(items, idx, cb) {
    this._simple_get(this.BASE + "add", cb, "POST", {items: JSON.stringify(items), idx});
  }

  remove(idx, count, cb) {
    console.log("remove idx", idx, "count", count);
    this._simple_get(this.BASE + "remove", cb, "POST", {idx, count});
  }

  move(idx, count, offs, cb) {
    console.log("move idx", idx, "count", count, "offs", offs);
    this._simple_get(this.BASE + "move", cb, "POST", {idx, count, offs});
  }

  start(cb, clearHistory) {
    this._simple_get(this.BASE + "start?clear_history=" + clearHistory, cb);
  }

  setLoop(looped) {
    this._simple_get(this.BASE + "set_loop?looped=" + looped);
  }
}
