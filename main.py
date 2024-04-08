from concurrent.futures import ThreadPoolExecutor
from contextvars import copy_context
from aiohttp import web
from aiohttp_sse import sse_response
from moesif_aiohttp import MoesifMiddleware
import asyncio
import functools
import json


def get_request_context():
    # Propagate the captured request global context to the executor. The context includes 'trace_id_var' generated at the aiohttp web app's middleware layer
    context = copy_context()
    return context.run


# Convert a URL into a Request JSON object
def convert_relative_url_to_json(relative_url):
    final_dict = {}
    query_dict = relative_url.query

    for key in iter(query_dict):
        value = query_dict.get(key)
        if value == "false":
            final_value = False
        elif value == "true":
            final_value = True
        elif value in ["null", "undefined"]:
            final_value = None
        else:
            final_value = value
        final_dict[key] = final_value

    return final_dict


async def wrapped_streaming_send(data, queue_cb, request_json, seen_events):
    try:
        await queue_cb(data[0], event=data[1])
    except Exception as e:
        print(
            f"sending data crash with error {str(e)} and data {data} and requests {request_json} and seen events {seen_events}"
        )
        raise


def non_streaming_event_loop(executor_name = "non_streaming_executor", has_request_body: bool = False):
    def _non_streaming_event_loop(cb):
        async def return_func(*args, **kwargs):
            request = args[-1]
            loop = asyncio.get_event_loop()
            executor = request.app[executor_name]
            if has_request_body:
                request_json = await request.json()
            else:
                request_json = convert_relative_url_to_json(request.rel_url)

            if len(args) == 1:
                wrapped_function = functools.partial(cb, request_json, **kwargs)
            else:
                wrapped_function = functools.partial(
                    cb, args[0], request_json, **kwargs
                )
            out = await loop.run_in_executor(
                executor, get_request_context(), wrapped_function
            )
            return out
        return return_func
    return _non_streaming_event_loop


def queue_consuming_event_loop(cb):
    executor_name = "streaming_executor"

    async def return_func(*args, **kwargs):
        request = args[-1]
        async with sse_response(request) as resp:
            queue = asyncio.Queue()
            loop = asyncio.get_event_loop()
            request_json = convert_relative_url_to_json(request.rel_url)

            queue_timeout = 5
            executor = request.app[executor_name]

            def async_enqueue(data):
                asyncio.run(queue.put(data))

            wrapped_function = functools.partial(
                cb, args[0], request_json, async_enqueue, **kwargs
            )
            loop.run_in_executor(executor, get_request_context(), wrapped_function)

            size = executor._work_queue.qsize()
            print(
                f"queue_consuming_event_loop using executor {executor_name}: the size of the queue is: {size}"
            )

            seen_events = []
            while True:
                try:
                    data = await asyncio.wait_for(queue.get(), timeout=queue_timeout)
                    seen_events.append(data[1])
                    await wrapped_streaming_send(
                        data, resp.send, request_json, seen_events
                    )
                    if data[1] == "done":
                        break
                except asyncio.TimeoutError:
                    print("Timed out waiting for the queue")
                    print(
                        f"queue_consuming_event_loop using executor {executor_name}: we exploded, when the size of the queue was: {executor._work_queue.qsize()}"
                    )
                    break
            return resp
    return return_func


class SearchService:
    @non_streaming_event_loop()
    def process_non_streaming_request(self, request_json):
        return web.json_response({"Echoed parsed inputs": str(request_json)})

    @queue_consuming_event_loop
    def process_streaming_request(self, request_json, enqueue_cb):
        enqueue_cb((str(request_json), "parsed inputs"))
        enqueue_cb(("data payload 1", "event 1"))
        enqueue_cb(("data payload 2", "event 2"))
        enqueue_cb(("data payload 3", "event 3"))
        enqueue_cb(("Finished", "done"))

async def ping(request):
    return web.Response(text="Ping success")

async def streaming_end_point(request):
    """
    Handler for the streaming API route.
    """
    response = web.StreamResponse(
        status=200,
        reason='OK',
        headers={
            'Content-Type': 'text/event-stream',
            'Cache-Control': 'no-cache',
            'Connection': 'keep-alive'
        }
    )
    await response.prepare(request)

    # Send events to the client
    await response.write(b'data: Hello, world!\n\n')
    await response.write(b'data: Goodbye, world!\n\n')
    await response.write(b'data: This is a streaming response.\n\n')

    return response


def identify_user(request, response):
    # Code to identify the user
    return "my-user"

def identify_company(request, response):
    # Code to identify the company
    return "my-company"

def get_token(request, response):
    return "XXXXXXXXXXXXXX"

def get_metadata(request, response):
    return {
            "schemas": ["ethereum", "polygon"],
            "tables": ["transactions"],
            "schema_tables": ["ethereum.transactions", "polygon.transactions"]
            }

def should_skip(request, response):
    return "POST" == request.method

def mask_event(eventmodel):
    # Your custom code to change or remove any sensitive fields
    if 'password' in eventmodel.request.body:
        eventmodel.request.body['password'] = None
    return eventmodel

moesif_settings = {
    'APPLICATION_ID': 'MOESIF_APPLICATION_ID',
    'DEBUG': False,
    'IDENTIFY_USER': identify_user,
    'IDENTIFY_COMPANY': identify_company,
    'GET_SESSION_TOKEN': get_token,
    'GET_METADATA': get_metadata,
    'SKIP': should_skip,
    'MASK_EVENT_MODEL': mask_event
}

def monolith_app():
    app = web.Application(
        middlewares=[MoesifMiddleware(moesif_settings)],
        client_max_size=3 * 1024**2,
        handler_args={"max_field_size": 32760, "max_line_size": 32760},
    )
    app["non_streaming_executor"] = ThreadPoolExecutor(max_workers=8)
    app["streaming_executor"] = ThreadPoolExecutor(max_workers=8)

    search_handler = SearchService()
    app.add_routes([
        web.get("/ping", ping),
        web.get("/streaming", streaming_end_point),
        web.get("/non_streaming_api", search_handler.process_non_streaming_request),
        web.get("/streaming_api", search_handler.process_streaming_request)
    ])
    return app


async def get_monolith():
    return monolith_app()
