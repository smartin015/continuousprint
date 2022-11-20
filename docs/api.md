# API

This plugin comes with a basic API to fetch state and start/stop the queue. This allows for other scripts and plugins to interact with the continuous print queue to unlock even more autonomous printing!

!!! important

    Other internal web requests exist than what's presented here, but they aren't for external use and are not guaranteed to be stable.

    If you want additional API features, [please submit a feature request](https://github.com/smartin015/continuousprint/issues/new?template=feature_request.md).

!!! tip "Tip: Usage Examples"

    See [`api_examples/`](https://github.com/smartin015/continuousprint/tree/master/api_examples) for reference implementations in different languages.

## Fetch the queue state

**Request**

**`HTTP GET http://printer:5000/plugin/continuousprint/state/get`**

Returns the current internal state of the printer as a JSON string. List entries within `queue` may include fields which are not listed here - those
fields may be subject to change without notice, so be wary of depending on them.

**Response**

```
{
  "active": true/false,
  "status": string,
  "statusType": string
  "profile": string,
  "queues": [
    {
      "name": string,
      "strategy": string,
      "jobs": [
        {
          "name": string,
          "count": int,
          "remaining" int,
          "draft": bool,
          "acquired": bool,
          "created" int,
          "id": int,
          "sets": [
            {
              "path": string,
              "count": int,
              "remaining": int,
              "materials": [...],
              "profiles": [...],
              "sd": bool
            },
            ...
          ]
        },
        ...
      ]
    },
    ...
  ]
}
```

## Add a set

**Request**

**`HTTP POST http://printer:5000/plugin/continuousprint/set/add`**

Adds a set, optionally creating an enclosing job if one is not specified.

Payload:

```
path: string
sd: bool
count: int
materials: list (optional)
profiles: list (optional)
job: int (optional ID of job)
jobName: string (optional)
jobDraft: bool (optional, default True)
```

**Response**

```
{
  "job_id": int,
  "set_": {
    // Fields matching set fields in /state/get
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


## Inject external data into preprocessor state

**Request**

**`HTTP POST http://printer:5000/plugin/continuousprint/automation/external`**

Payload: any [JSON](https://www.w3schools.com/js/js_json_intro.asp) dictionary object, e.g. `{"a": 1, "b": "hello"}`

This makes external data available to [Preprocessors](/gcode-scripting.md).

**Response**

`OK` if the data was successfully injected.
