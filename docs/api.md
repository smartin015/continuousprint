# Continuous Print API

This plugin comes with a basic API to fetch state and start/stop the queue. This allows for other scripts and plugins to interact with the continuous print queue to unlock even more autonomous printing!

!!! important

    Other internal web requests exist than what's presented here, but they aren't for external use and are not guaranteed to be stable.

    If you want additional API features, [please submit a feature request](https://github.com/smartin015/continuousprint/issues/new?template=feature_request.md).

!!! tip "Tip: Usage Examples"

    See [`api_examples/`](https://github.com/smartin015/continuousprint/tree/master/api_examples) for reference implementations in different languages.

## Fetch the queue state

**Request**

**`HTTP GET http://printer:5000/plugin/continuousprint/state`**

Returns the current internal state of the printer as a JSON string. List entries within `queue` may include fields which are not listed here - those
fields may be subject to change without notice, so be wary of depending on them.

**Response**

```
{
  "active": true/false,
  "status": string,
  "queue": [
    {
      "name": string,
      "path": string,
      "sd": bool
      "job": string,
      "run": number
      "start_ts": null | number (seconds),
      "end_ts": null | number (seconds),
      "result": string (todo specific stirngs),
      "retries": number
    },
    ...
  ]
}
```

## Start/stop managing the queue

**Request**

**`HTTP POST http://printer:5000/plugin/continuousprint/set_active`**

Payload: `active=true` or `active=false`

This starts and stops continuous print management of the printer.

!!! warning

    If `active=false` is sent, the plugin will stop managing the queue **but it will not stop any currently active print**. This must be done separately.

    See [the OctoPrint REST API](https://docs.octoprint.org/en/master/api/job.html#issue-a-job-command) for additional print job management options which include cancelling active prints.

**Response**

Same as `/state` above
