import asyncio
import copy
import inspect
import json
import logging
import structlog
import time
from asyncio import Queue, CancelledError
from sanic import Blueprint, response
from sanic.request import Request
from sanic.response import HTTPResponse, ResponseStream
from typing import Text, Dict, Any, Optional, Callable, Awaitable, NoReturn, Union

import rasa.utils.endpoints
from rasa.core.channels.channel import (
    InputChannel,
    CollectingOutputChannel,
    UserMessage,
)


logger = logging.getLogger(__name__)
structlogger = structlog.get_logger()


class ChatInput(InputChannel):
    """A custom http input channel.

    This implementation is the basis for a custom implementation of a chat
    frontend. You can customize this to send messages to Rasa and
    retrieve responses from the assistant.
    """

    @classmethod
    def name(cls) -> Text:
        return "chat"

    async def _extract_ip(self, req: Request) -> Optional[Text]:
        return req.json.get("remote_addr", None)

    async def _extract_sender(self, req: Request) -> Optional[Text]:
        return req.json.get("user", None)

    # noinspection PyMethodMayBeStatic
    def _extract_message(self, req: Request) -> Optional[Text]:
        # this function extracts the last `user` message from the chat completions messages array
        # and returns the `user` field from it
        # if the chat completions messages array is empty, it returns None
        messages = req.json.get("messages", None)
        if messages is None:
            return None
        for message in reversed(messages):
            if message.get("role") == "user":
                return message.get("content", None)
        return None

    def _extract_input_channel(self, req: Request) -> Text:
        return req.json.get("input_channel") or self.name()

    def get_metadata(self, request: Request) -> Optional[Dict[Text, Any]]:
        """Extracts additional information from the incoming request.

         Implementing this function is not required. However, it can be used to extract
         metadata from the request. The return value is passed on to the
         ``UserMessage`` object and stored in the conversation tracker.

        Args:
            request: incoming request with the message of the user

        Returns:
            Metadata which was extracted from the request.
        """
        return request.json.get("metadata", None)

    def _collector_to_completion_response(self, collector: CollectingOutputChannel) -> Dict[Text, Any]:
        """Convert the output of a message collector to a response the user."""
        # this function converts the messages from the `collector` to a response that will be sent back to the user
        # the response is a dictionary with a single key `messages` which contains the messages from the `collector`
        # {
        #   "id": "chatcmpl-123",
        #   "object": "chat.completion",
        #   "created": 1677652288,
        #   "model": "gpt-3.5-turbo-0125",
        #   "system_fingerprint": "fp_44709d6fcb",
        #   "choices": [{
        #     "index": 0,
        #     "message": {
        #       "role": "assistant",
        #       "content": "\n\nHello there, how may I assist you today?",
        #     },
        #     "logprobs": null,
        #     "finish_reason": "stop"
        #   }],
        #   "usage": {
        #     "prompt_tokens": 9,
        #     "completion_tokens": 12,
        #     "total_tokens": 21
        #   }
        # }
        # [{'recipient_id': '<coroutine object ChatInput._extract_ip at 0x3230f5d20>', 'text': 'Bye'}]
        response = {
            "id": "",
            "object": "chat.completion",
            # unix timestamp
            "created": int(time.time()),
            "model": "rasa",
            "choices": [{
                "index": 0,
                "message": {
                    "role": "assistant",
                    "content": collector.messages[0].get("text")
                },
                "logprobs": None,
                "finish_reason": "stop"
            }],
            "usage": {
                "prompt_tokens": 0,
                "completion_tokens": 0,
                "total_tokens": 0
            }
        }

        return response

    def blueprint(
        self, on_new_message: Callable[[UserMessage], Awaitable[None]]
    ) -> Blueprint:
        """Groups the collection of endpoints used by rest channel."""
        module_type = inspect.getmodule(self)
        if module_type is not None:
            module_name = module_type.__name__
        else:
            module_name = None

        custom_webhook = Blueprint(
            "custom_webhook_{}".format(type(self).__name__),
            module_name,
        )

        # noinspection PyUnusedLocal
        @custom_webhook.route("/", methods=["GET"])
        async def health(request: Request) -> HTTPResponse:
            return response.json({"status": "ok"})

        @custom_webhook.route("/webhook", methods=["POST"])
        async def receive(request: Request) -> Union[ResponseStream, HTTPResponse]:
            sender_id = await self._extract_sender(request)
            if sender_id is None:
                sender_id = self._extract_ip(request)
            text = self._extract_message(request)
            input_channel = self._extract_input_channel(request)
            metadata = self.get_metadata(request)

            collector = CollectingOutputChannel()
            # noinspection PyBroadException
            try:
                await on_new_message(
                    UserMessage(
                        text,
                        collector,
                        sender_id,
                        input_channel=input_channel,
                        metadata=metadata,
                        headers=request.headers,
                    )
                )
            except CancelledError:
                structlogger.error(
                    "chat.message.received.timeout", text=copy.deepcopy(text)
                )
            except Exception:
                structlogger.exception(
                    "chat.message.received.failure", text=copy.deepcopy(text)
                )

            completion_response = self._collector_to_completion_response(collector)
            # return response.json(collector.messages)
            return response.json(completion_response)

        return custom_webhook
