# Moesif AIOHTTP Example with Moesif Integrated

[Moesif](https://www.moesif.com) is an API analytics platform.
[moesif-aiohttp](https://github.com/Moesif/moesif-aiohttp)
is a middleware that logs API calls to Moesif for AIOHTTP based application.

This example is an application with Moesif's API analytics and monitoring integrated.

## Setup

Install dependencies by `pip install -r requirements.txt`

You will also want to set the `MOESIF_APPLICATION_ID` in the `moesif_settings` with the value being your 
application id from your Moesif account in the `main.py`

## How to run

Run Gunicorn server
```bash
gunicorn --reload main:get_monolith --worker-class aiohttp.GunicornWebWorker --workers 1 --threads=8 --timeout 1200
```

## Running against APIs

### Non-streaming request

Running this
```bash
curl http://localhost:8000/non_streaming_api\?hello=world
```

Should give you
```
{"Echoed parsed inputs": "{'hello': 'world'}"}
```

### Streaming request

Running this
```bash
curl http://localhost:8000/streaming_api\?hello=world
```

Should give you
```
event: parsed inputs
data: {'hello': 'world'}

event: event 1
data: data payload 1

event: event 2
data: data payload 2

event: event 3
data: data payload 3

event: done
data: Finished
```
The API Calls should show up in Moesif.
