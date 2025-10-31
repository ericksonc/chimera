#!/usr/bin/env python3
"""Test script to check if /stream endpoint works with our fix."""

import json
import requests

# Exact request body from api/requests.log
request_body = {
  "thread_protocol": [
    {
      "event_type": "thread_blueprint",
      "timestamp": "2025-10-31T07:37:37.549680+00:00",
      "thread_id": "c665fffe-8260-48df-babc-5be12f308eb0",
      "blueprint_version": "0.0.1",
      "blueprint": {
        "space": {
          "type": "reference",
          "class_name": "chimera.spaces.GenericSpace",
          "version": "1.0.0",
          "config": {
            "agent_id": "e9c226ce-2736-4bd7-be3a-f9b31550cec6"
          },
          "widgets": []
        },
        "agents": [
          {
            "type": "inline",
            "id": "e9c226ce-2736-4bd7-be3a-f9b31550cec6",
            "name": "Jarvis",
            "description": "Your own personal Jarvis.",
            "base_prompt": "# PERSONA\nYou are Jarvis, a helpful and professional assistant.\nYou prioritize clarity and accuracy in your responses.\n# INTERACTION PARADIGM\nYou are an assistant inside of a smartphone app. It acts like a voice memo- always recording- but the assistant is only triggered to respond\nwhen the user says the wake word \"Hey Jarvis\" - on-device ONNX models detect the wakeword, and trigger you.\nThe system is in early rapid prototyping mode. \nRemember that you're always seeing a transcript. It's part of your job to recognize that the transcription may be rough, and do your best\nto mentally translate what's written as the transcript to what the user most likely actually said.\n# USING YOUR voice\nThe app you are part of is designed for *hands free, voice to voice communication.*\nWhat you write is spoken via ElevenLabs TTS.\nThis means you must ONLY produce \"speech\" - do NOT attempt to \"narrate\" roleplay- e.g. \"*slight electronic static crackle*\" - outputting\nthis would cause Jarvis to actually *speak* those words, which doesn't have the desired effect at all. \nIn other words: All \"dialogue\" no \"scene description.\"\nThe voice we're using sounds very much like your fictional namesake Jarvis; accent, soft vocoder effect and all, so consider that your\n\"instrument\" to play. ",
            "widgets": [
              {
                "class_name": "chimera.widgets.ContextDocsWidget",
                "version": "1.0.0",
                "instance_id": "context_docs_inst1",
                "config": {
                  "base_path": "/Users/ericksonc/appdev/chimera",
                  "whitelist_paths": [
                    "core/protocols/",
                    "meta/agents/architecture/"
                  ],
                  "blacklist_paths": [
                    "meta/agents/architecture/archive/"
                  ]
                }
              }
            ]
          }
        ]
      }
    }
  ],
  "user_input": "hi jarvis, do u read me?"
}

print("Testing /stream endpoint (should stream SSE events)...")
print("=" * 80)

try:
    response = requests.post(
        "http://localhost:33003/stream",
        json=request_body,
        headers={
            "Content-Type": "application/json",
            "Accept": "text/event-stream"
        },
        stream=True  # Important for SSE
    )

    print(f"Status Code: {response.status_code}")

    if response.status_code == 200:
        print("SUCCESS! Streaming response:")
        print("-" * 80)
        # Read first few SSE events
        count = 0
        for line in response.iter_lines():
            if line:
                print(line.decode('utf-8'))
                count += 1
                if count > 10:  # Just show first 10 events
                    print("... (truncated, stream working)")
                    break
    else:
        print(f"ERROR! Response body:")
        print(response.text)

except Exception as e:
    print(f"Error: {e}")
