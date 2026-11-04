/*
 * This file is part of phomemo-printer-app.
 * Copyright (C) 2026 Paul Bütof, Passionate Bytes Solutions
 *
 * phomemo-printer-app is free software: you can redistribute it and/or modify
 * it under the terms of the GNU General Public License as published by
 * the Free Software Foundation, either version 3 of the License, or
 * (at your option) any later version.
 *
 * phomemo-printer-app is distributed in the hope that it will be useful,
 * but WITHOUT ANY WARRANTY; without even the implied warranty of
 * MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
 * GNU General Public License for more details.
 *
 * You should have received a copy of the GNU General Public License
 * along with phomemo-printer-app.  If not, see <https://www.gnu.org/licenses/>.
 */

// Client side of the phomemo-bridge socket protocol.
//
// Every message is one JSON object on its own line. A message carrying
// raw bytes states their length in "bytes" and the bytes follow the
// newline immediately. The bridge answers each request with exactly one
// reply ({"ok": true, ...} or {"ok": false, "error": ...}) and may push
// {"event": ...} messages before the reply.

#ifndef PHOMEMO_BRIDGE_H
#define PHOMEMO_BRIDGE_H

#include <stdbool.h>
#include <stddef.h>

#include "cJSON.h"

#define PHOMEMO_BRIDGE_MAX_LINE (64 * 1024)
#define PHOMEMO_BRIDGE_MAX_PAYLOAD (16 * 1024 * 1024)

typedef struct
{
  int fd;            // connected socket, -1 when closed
  char *line;        // receive buffer
  size_t line_size;  // allocated size of line
  size_t line_len;   // bytes buffered but not yet consumed
  char pending[32];  // cmd of the request awaiting its reply
} phomemo_bridge_t;

// Called for each pushed event received while waiting for a reply, and
// with a NULL event about once a second while nothing arrives so the
// caller can notice a cancelled job. An event object is freed after the
// callback returns.
typedef void (*phomemo_event_cb_t)(cJSON *event, void *data);

// Connects to the bridge socket. On failure writes a message to err and
// returns false.
bool phomemo_bridge_connect(phomemo_bridge_t *b, const char *socket_path,
                            char *err, size_t errsize);

// Closes the socket and frees the receive buffer. Safe on a closed bridge.
// A transport failure (EOF, read or write error) closes the socket on its
// own: fd becomes -1 and later calls fail with "bridge not connected"
// until the owner reconnects.
void phomemo_bridge_close(phomemo_bridge_t *b);

// Sends one request. When payload_len > 0 the message gets a "bytes"
// field and the payload follows the line. The request object stays the
// caller's.
bool phomemo_bridge_send(phomemo_bridge_t *b, cJSON *request,
                         const void *payload, size_t payload_len,
                         char *err, size_t errsize);

// Reads events (passing each to on_event) until the reply arrives. Returns
// the reply object when "ok" is true; the caller frees it. Returns NULL
// with the bridge's error text (or a transport error) in err otherwise.
// The bridge answers an "abort" sent while another command is pending
// with its own reply first; that reply is skipped here.
cJSON *phomemo_bridge_reply(phomemo_bridge_t *b, phomemo_event_cb_t on_event,
                            void *data, char *err, size_t errsize);

// phomemo_bridge_send followed by phomemo_bridge_reply.
cJSON *phomemo_bridge_call(phomemo_bridge_t *b, cJSON *request,
                           const void *payload, size_t payload_len,
                           phomemo_event_cb_t on_event, void *data,
                           char *err, size_t errsize);

#endif // PHOMEMO_BRIDGE_H
