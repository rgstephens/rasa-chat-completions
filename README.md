# Rasa Chat Completions Channel

This is a Rasa channel that support the OpenAI [Chat Completions API](https://platform.openai.com/docs/guides/text-generation/chat-completions-api).

The idea is that there are many tools being written for the chat completions API and it would be nice to be able to use these with a Rasa bot.

## Differences

Since the chat completions API is designed for use with OpenAI models not a Rasa bot, some of the differences in the implementation for Rasa are:

- The Rasa channel will only process the most recent `user` message in the `messages` array
- The chat completions `user` is mapped to the Rasa `sender_id`. (Not sure what we will do if the `user` key is not provided)
- The [chat completion object](https://platform.openai.com/docs/api-reference/chat/object) supports a subset of the values returned by OpenAI

## Installation

To use the channel place the `chat.py` file in a directory in your project and configure your `credentials.yml` to reference it. If you place the file in a directory called `custom` the entry `credentials.yml` entry would be:

```yml
custom.chat.ChatInput:
```

## Example Tools

- [garak](https://github.com/leondz/garak) LLM Vulnerability Scanner
- [deep-chat](https://github.com/OvidijusParsiunas/deep-chat) chat widget
- [uptrain](https://github.com/uptrain-ai/uptrain) evaluation and testing tool
