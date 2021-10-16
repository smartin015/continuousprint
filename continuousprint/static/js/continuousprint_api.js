

class CPrintAPI {
  BASE = "plugin/continuousprint/"

  _simple_get(url, cb, type) {
    $.ajax({
        url: url,
        type: "GET",
        dataType: type || "json",
        headers: {"X-Api-Key":UI_API_KEY},
        success: cb,
    });
  }

  getState(cb) {
    this._simple_get(this.BASE + "state", cb);
  }

  getFileList(cb) {
    this._simple_get("/api/files?recursive=true", cb);
  }

  add(data, cb, err) {
    $.ajax({
        url: this.BASE + "add",
        type: "POST",
        dataType: "text",
        headers: {
            "X-Api-Key":UI_API_KEY,
        },
        data: data,
        success: cb,
        error: err,
    });
  }

  move(src, dest, cb) {
    this._simple_get(this.BASE + "move?src=" + src + "&dest=" + dest, cb);
  }

  changeCount(idx, count, cb) {
    this._simple_get(this.BASE + "change?index=" + idx + "&count=" + count, cb);
  }

  remove(idx, cb) {
    $.ajax({
        url: this.BASE + "removequeue?index=" + idx,
        type: "DELETE",
        dataType: "text",
        headers: {
            "X-Api-Key":UI_API_KEY,
        },
        success: cb,
        error: cb, 
    });
  }

  start(cb, clearHistory) {
    this._simple_get(this.BASE + "start?clear_history=" + clearHistory, cb);
  }

  setLoop(looped) {
    this._simple_get(this.BASE + "set_loop?looped=" + looped);
  }
}
