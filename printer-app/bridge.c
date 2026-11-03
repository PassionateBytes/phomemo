// Client side of the phomemo-bridge socket protocol.

#include "bridge.h"

#include <errno.h>
#include <poll.h>
#include <stdarg.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <sys/socket.h>
#include <sys/un.h>
#include <unistd.h>

static void
set_error(char *err, size_t errsize, const char *fmt, ...)
{
  va_list ap;

  if (!err || !errsize)
    return;
  va_start(ap, fmt);
  vsnprintf(err, errsize, fmt, ap);
  va_end(ap);
}

// Forgets a socket the other side has dropped so later calls report
// "not connected" and the owner can reconnect.
static void
drop_link(phomemo_bridge_t *b)
{
  if (b->fd >= 0)
    close(b->fd);
  b->fd = -1;
  b->line_len = 0;
  b->pending[0] = '\0';
}

bool
phomemo_bridge_connect(phomemo_bridge_t *b, const char *socket_path,
                       char *err, size_t errsize)
{
  struct sockaddr_un addr;

  memset(b, 0, sizeof(*b));
  b->fd = -1;

  if (strlen(socket_path) >= sizeof(addr.sun_path))
  {
    set_error(err, errsize, "socket path %s is too long", socket_path);
    return false;
  }

  int fd = socket(AF_UNIX, SOCK_STREAM | SOCK_CLOEXEC, 0);
  if (fd < 0)
  {
    set_error(err, errsize, "socket: %s", strerror(errno));
    return false;
  }

  memset(&addr, 0, sizeof(addr));
  addr.sun_family = AF_UNIX;
  strcpy(addr.sun_path, socket_path);
  if (connect(fd, (struct sockaddr *)&addr, sizeof(addr)) < 0)
  {
    set_error(err, errsize, "connect %s: %s", socket_path, strerror(errno));
    close(fd);
    return false;
  }

  b->fd = fd;
  return true;
}

void
phomemo_bridge_close(phomemo_bridge_t *b)
{
  if (b->fd >= 0)
    close(b->fd);
  free(b->line);
  b->fd = -1;
  b->line = NULL;
  b->line_size = 0;
  b->line_len = 0;
}

static bool
write_all(phomemo_bridge_t *b, const void *data, size_t len, char *err,
          size_t errsize)
{
  const char *p = data;
  while (len)
  {
    ssize_t n = send(b->fd, p, len, MSG_NOSIGNAL);
    if (n < 0)
    {
      if (errno == EINTR)
        continue;
      set_error(err, errsize, "write: %s", strerror(errno));
      drop_link(b);
      return false;
    }
    p += n;
    len -= (size_t)n;
  }
  return true;
}

bool
phomemo_bridge_send(phomemo_bridge_t *b, cJSON *request, const void *payload,
                    size_t payload_len, char *err, size_t errsize)
{
  if (b->fd < 0)
  {
    set_error(err, errsize, "bridge not connected");
    return false;
  }

  cJSON *message = request;
  if (payload_len > 0)
  {
    message = cJSON_Duplicate(request, true);
    if (!message || !cJSON_AddNumberToObject(message, "bytes",
                                             (double)payload_len))
    {
      cJSON_Delete(message);
      set_error(err, errsize, "out of memory");
      return false;
    }
  }

  char *text = cJSON_PrintUnformatted(message);
  if (message != request)
    cJSON_Delete(message);
  if (!text)
  {
    set_error(err, errsize, "out of memory");
    return false;
  }

  cJSON *cmd = cJSON_GetObjectItem(request, "cmd");
  if (cJSON_IsString(cmd) && strcmp(cmd->valuestring, "abort"))
    snprintf(b->pending, sizeof(b->pending), "%s", cmd->valuestring);

  size_t text_len = strlen(text);
  text[text_len++] = '\n';  // cJSON allocates room for the terminator
  bool ok = write_all(b, text, text_len, err, errsize);
  free(text);
  if (ok && payload_len > 0)
    ok = write_all(b, payload, payload_len, err, errsize);
  return ok;
}

// Reads until the buffer holds a complete line. Returns the length of the
// line without its newline, or -1 on error.
static ssize_t
fill_line(phomemo_bridge_t *b, char *err, size_t errsize)
{
  for (;;)
  {
    char *nl = memchr(b->line, '\n', b->line_len);
    if (nl)
      return nl - b->line;

    if (b->line_len >= PHOMEMO_BRIDGE_MAX_LINE)
    {
      set_error(err, errsize, "bridge sent an over-long line");
      return -1;
    }

    if (b->line_len == b->line_size)
    {
      size_t size = b->line_size ? b->line_size * 2 : 4096;
      char *line = realloc(b->line, size);
      if (!line)
      {
        set_error(err, errsize, "out of memory");
        return -1;
      }
      b->line = line;
      b->line_size = size;
    }

    ssize_t n = read(b->fd, b->line + b->line_len,
                     b->line_size - b->line_len);
    if (n < 0)
    {
      if (errno == EINTR)
        continue;
      set_error(err, errsize, "read: %s", strerror(errno));
      drop_link(b);
      return -1;
    }
    if (n == 0)
    {
      set_error(err, errsize, "bridge closed the connection");
      drop_link(b);
      return -1;
    }
    b->line_len += (size_t)n;
  }
}

// Drops the first `count` buffered bytes.
static void
consume(phomemo_bridge_t *b, size_t count)
{
  memmove(b->line, b->line + count, b->line_len - count);
  b->line_len -= count;
}

// Skips a payload the bridge attached to a message.
static bool
discard_payload(phomemo_bridge_t *b, size_t size, char *err, size_t errsize)
{
  while (size)
  {
    if (b->line_len)
    {
      size_t take = b->line_len < size ? b->line_len : size;
      consume(b, take);
      size -= take;
      continue;
    }
    char scratch[4096];
    size_t want = size < sizeof(scratch) ? size : sizeof(scratch);
    ssize_t n = read(b->fd, scratch, want);
    if (n < 0)
    {
      if (errno == EINTR)
        continue;
      set_error(err, errsize, "read: %s", strerror(errno));
      drop_link(b);
      return false;
    }
    if (n == 0)
    {
      set_error(err, errsize, "bridge closed the connection");
      drop_link(b);
      return false;
    }
    size -= (size_t)n;
  }
  return true;
}

// Reads one message object. Any attached payload is discarded.
static cJSON *
read_message(phomemo_bridge_t *b, char *err, size_t errsize)
{
  ssize_t len = fill_line(b, err, errsize);
  if (len < 0)
    return NULL;

  cJSON *obj = cJSON_ParseWithLength(b->line, (size_t)len);
  consume(b, (size_t)len + 1);
  if (!obj || !cJSON_IsObject(obj))
  {
    cJSON_Delete(obj);
    set_error(err, errsize, "bridge sent malformed JSON");
    return NULL;
  }

  cJSON *bytes = cJSON_GetObjectItem(obj, "bytes");
  if (bytes)
  {
    double size = cJSON_IsNumber(bytes) ? bytes->valuedouble : -1;
    if (size < 0 || size > PHOMEMO_BRIDGE_MAX_PAYLOAD ||
        !discard_payload(b, (size_t)size, err, errsize))
    {
      cJSON_Delete(obj);
      if (size < 0 || size > PHOMEMO_BRIDGE_MAX_PAYLOAD)
        set_error(err, errsize, "bridge sent an invalid payload length");
      return NULL;
    }
  }
  return obj;
}

// Waits up to one second for data. Returns 1 when readable, 0 on timeout,
// -1 on error.
static int
wait_readable(phomemo_bridge_t *b, char *err, size_t errsize)
{
  struct pollfd pfd = {b->fd, POLLIN, 0};
  int n = poll(&pfd, 1, 1000);
  if (n < 0)
  {
    if (errno == EINTR)
      return 0;
    set_error(err, errsize, "poll: %s", strerror(errno));
    drop_link(b);
  }
  return n;
}

cJSON *
phomemo_bridge_reply(phomemo_bridge_t *b, phomemo_event_cb_t on_event,
                     void *data, char *err, size_t errsize)
{
  if (b->fd < 0)
  {
    set_error(err, errsize, "bridge not connected");
    return NULL;
  }

  for (;;)
  {
    if (!memchr(b->line, '\n', b->line_len))
    {
      int ready = wait_readable(b, err, errsize);
      if (ready < 0)
        return NULL;
      if (ready == 0)
      {
        if (on_event)
          on_event(NULL, data);
        continue;
      }
    }

    cJSON *obj = read_message(b, err, errsize);
    if (!obj)
      return NULL;

    if (cJSON_HasObjectItem(obj, "event"))
    {
      if (on_event)
        on_event(obj, data);
      cJSON_Delete(obj);
      continue;
    }

    cJSON *cmd = cJSON_GetObjectItem(obj, "cmd");
    if (cJSON_IsString(cmd) && !strcmp(cmd->valuestring, "abort") &&
        strcmp(b->pending, "abort"))
    {
      cJSON_Delete(obj);
      continue;
    }

    cJSON *ok = cJSON_GetObjectItem(obj, "ok");
    if (cJSON_IsTrue(ok))
      return obj;

    cJSON *error = cJSON_GetObjectItem(obj, "error");
    if (cJSON_IsString(error) && error->valuestring[0])
      set_error(err, errsize, "%s", error->valuestring);
    else if (cJSON_IsFalse(ok))
      set_error(err, errsize, "bridge reported an error");
    else
      set_error(err, errsize, "bridge sent an unexpected message");
    cJSON_Delete(obj);
    return NULL;
  }
}

cJSON *
phomemo_bridge_call(phomemo_bridge_t *b, cJSON *request, const void *payload,
                    size_t payload_len, phomemo_event_cb_t on_event,
                    void *data, char *err, size_t errsize)
{
  if (!phomemo_bridge_send(b, request, payload, payload_len, err, errsize))
    return NULL;
  return phomemo_bridge_reply(b, on_event, data, err, errsize);
}
