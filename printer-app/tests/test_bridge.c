// Unit tests of the bridge client. A forked child plays the bridge on the
// other end of a socketpair; a child that trips an assert exits nonzero and
// the parent reports it.

#include "bridge.h"

#include <assert.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <sys/socket.h>
#include <sys/wait.h>
#include <unistd.h>

typedef void (*server_fn)(int fd);

static pid_t server_pid;

static phomemo_bridge_t
start_server(server_fn fn)
{
  int sv[2];
  assert(socketpair(AF_UNIX, SOCK_STREAM, 0, sv) == 0);
  server_pid = fork();
  assert(server_pid >= 0);
  if (server_pid == 0)
  {
    close(sv[0]);
    fn(sv[1]);
    close(sv[1]);
    _exit(0);
  }
  close(sv[1]);
  phomemo_bridge_t b = {sv[0], NULL, 0, 0, ""};
  return b;
}

static void
stop_server(phomemo_bridge_t *b)
{
  int status = -1;
  phomemo_bridge_close(b);
  assert(waitpid(server_pid, &status, 0) == server_pid);
  assert(WIFEXITED(status) && WEXITSTATUS(status) == 0);
}

static void
write_all(int fd, const char *s)
{
  size_t len = strlen(s);
  while (len)
  {
    ssize_t n = write(fd, s, len);
    assert(n > 0);
    s += n;
    len -= (size_t)n;
  }
}

static void
read_exact(int fd, char *buf, size_t len)
{
  while (len)
  {
    ssize_t n = read(fd, buf, len);
    assert(n > 0);
    buf += n;
    len -= (size_t)n;
  }
}

// Reads one line (without the newline) into buf.
static void
read_line(int fd, char *buf, size_t size)
{
  size_t i = 0;
  for (;;)
  {
    char c;
    assert(read(fd, &c, 1) == 1);
    if (c == '\n')
      break;
    assert(i + 1 < size);
    buf[i++] = c;
  }
  buf[i] = '\0';
}

static void
on_event(cJSON *event, void *data)
{
  int *percent = data;
  cJSON *p = cJSON_GetObjectItem(event, "percent");
  assert(cJSON_IsNumber(p));
  *percent = (int)p->valuedouble;
}

static void
server_event_then_reply(int fd)
{
  char line[256];
  read_line(fd, line, sizeof(line));
  assert(strstr(line, "\"cmd\":\"page_end\""));
  write_all(fd, "{\"event\":\"progress\",\"percent\":50}\n"
                "{\"ok\":true,\"cmd\":\"page_end\",\"impressions\":1}\n");
}

static void
test_event_then_reply(void)
{
  phomemo_bridge_t b = start_server(server_event_then_reply);
  cJSON *req = cJSON_CreateObject();
  cJSON_AddStringToObject(req, "cmd", "page_end");
  char err[128] = "";
  int percent = -1;
  cJSON *reply = phomemo_bridge_call(&b, req, NULL, 0, on_event, &percent,
                                     err, sizeof(err));
  assert(reply != NULL);
  assert(percent == 50);
  cJSON *imp = cJSON_GetObjectItem(reply, "impressions");
  assert(cJSON_IsNumber(imp) && imp->valueint == 1);
  cJSON_Delete(reply);
  cJSON_Delete(req);
  stop_server(&b);
}

static void
server_error_reply(int fd)
{
  char line[256];
  read_line(fd, line, sizeof(line));
  write_all(fd, "{\"ok\":false,\"cmd\":\"open\",\"error\":\"busy\"}\n");
}

static void
test_error_reply(void)
{
  phomemo_bridge_t b = start_server(server_error_reply);
  cJSON *req = cJSON_CreateObject();
  cJSON_AddStringToObject(req, "cmd", "open");
  char err[128] = "";
  cJSON *reply = phomemo_bridge_call(&b, req, NULL, 0, NULL, NULL, err,
                                     sizeof(err));
  assert(reply == NULL);
  assert(strcmp(err, "busy") == 0);
  cJSON_Delete(req);
  stop_server(&b);
}

static void
server_payload(int fd)
{
  char line[256];
  char payload[420];
  read_line(fd, line, sizeof(line));
  cJSON *obj = cJSON_Parse(line);
  assert(obj != NULL);
  cJSON *bytes = cJSON_GetObjectItem(obj, "bytes");
  assert(cJSON_IsNumber(bytes) && bytes->valueint == 420);
  cJSON *count = cJSON_GetObjectItem(obj, "count");
  assert(cJSON_IsNumber(count) && count->valueint == 2);
  cJSON_Delete(obj);
  read_exact(fd, payload, sizeof(payload));
  for (size_t i = 0; i < sizeof(payload); i++)
    assert(payload[i] == (char)(i & 0xff));
  write_all(fd, "{\"ok\":true,\"cmd\":\"lines\"}\n");
}

static void
test_payload(void)
{
  phomemo_bridge_t b = start_server(server_payload);
  unsigned char payload[420];
  for (size_t i = 0; i < sizeof(payload); i++)
    payload[i] = (unsigned char)(i & 0xff);
  cJSON *req = cJSON_CreateObject();
  cJSON_AddStringToObject(req, "cmd", "lines");
  cJSON_AddNumberToObject(req, "count", 2);
  char err[128] = "";
  cJSON *reply = phomemo_bridge_call(&b, req, payload, sizeof(payload), NULL,
                                     NULL, err, sizeof(err));
  assert(reply != NULL);
  assert(cJSON_GetObjectItem(req, "bytes") == NULL);
  cJSON_Delete(reply);
  cJSON_Delete(req);
  stop_server(&b);
}

static void
server_split_write(int fd)
{
  char line[256];
  read_line(fd, line, sizeof(line));
  write_all(fd, "{\"ok\":true,\"cmd\":\"sta");
  usleep(20000);
  write_all(fd, "tus\",\"paper\":true}\n");
}

static void
test_reply_arrives_in_pieces(void)
{
  phomemo_bridge_t b = start_server(server_split_write);
  cJSON *req = cJSON_CreateObject();
  cJSON_AddStringToObject(req, "cmd", "status");
  char err[128] = "";
  cJSON *reply = phomemo_bridge_call(&b, req, NULL, 0, NULL, NULL, err,
                                     sizeof(err));
  assert(reply != NULL);
  assert(cJSON_IsTrue(cJSON_GetObjectItem(reply, "paper")));
  cJSON_Delete(reply);
  cJSON_Delete(req);
  stop_server(&b);
}

static void
server_hangs_up(int fd)
{
  char line[256];
  read_line(fd, line, sizeof(line));
}

static void
test_eof_is_an_error(void)
{
  phomemo_bridge_t b = start_server(server_hangs_up);
  cJSON *req = cJSON_CreateObject();
  cJSON_AddStringToObject(req, "cmd", "status");
  char err[128] = "";
  cJSON *reply = phomemo_bridge_call(&b, req, NULL, 0, NULL, NULL, err,
                                     sizeof(err));
  assert(reply == NULL);
  assert(err[0] != '\0');
  cJSON_Delete(req);
  stop_server(&b);
}

static void
server_abort_reply_first(int fd)
{
  char line[256];
  read_line(fd, line, sizeof(line));
  assert(strstr(line, "\"cmd\":\"wait_ready\""));
  read_line(fd, line, sizeof(line));
  assert(strstr(line, "\"cmd\":\"abort\""));
  write_all(fd, "{\"ok\":true,\"cmd\":\"abort\"}\n"
                "{\"ok\":false,\"cmd\":\"wait_ready\",\"error\":\"cancelled\"}\n");
}

// The abort reply arrives before the pending command's reply and must not
// be mistaken for it.
static void
test_abort_reply_is_skipped(void)
{
  phomemo_bridge_t b = start_server(server_abort_reply_first);
  cJSON *req = cJSON_CreateObject();
  cJSON_AddStringToObject(req, "cmd", "wait_ready");
  cJSON *abort = cJSON_CreateObject();
  cJSON_AddStringToObject(abort, "cmd", "abort");
  char err[128] = "";
  assert(phomemo_bridge_send(&b, req, NULL, 0, err, sizeof(err)));
  assert(phomemo_bridge_send(&b, abort, NULL, 0, err, sizeof(err)));
  cJSON *reply = phomemo_bridge_reply(&b, NULL, NULL, err, sizeof(err));
  assert(reply == NULL);
  assert(strcmp(err, "cancelled") == 0);
  cJSON_Delete(req);
  cJSON_Delete(abort);
  stop_server(&b);
}

static void
server_slow_reply(int fd)
{
  char line[256];
  read_line(fd, line, sizeof(line));
  usleep(1500000);
  write_all(fd, "{\"ok\":true,\"cmd\":\"wait_ready\"}\n");
}

static void
count_ticks(cJSON *event, void *data)
{
  int *ticks = data;
  if (event == NULL)
    (*ticks)++;
}

// While a reply is outstanding the callback is invoked with NULL about
// once a second so the caller can notice a cancelled job.
static void
test_reply_ticks_while_waiting(void)
{
  phomemo_bridge_t b = start_server(server_slow_reply);
  cJSON *req = cJSON_CreateObject();
  cJSON_AddStringToObject(req, "cmd", "wait_ready");
  char err[128] = "";
  int ticks = 0;
  cJSON *reply = phomemo_bridge_call(&b, req, NULL, 0, count_ticks, &ticks, err,
                                     sizeof(err));
  assert(reply != NULL);
  assert(ticks >= 1);
  cJSON_Delete(reply);
  cJSON_Delete(req);
  stop_server(&b);
}

static void
test_connect_missing_socket(void)
{
  phomemo_bridge_t b;
  char err[128] = "";
  assert(!phomemo_bridge_connect(&b, "/nonexistent/phomemo-bridge.sock", err,
                                 sizeof(err)));
  assert(err[0] != '\0');
  assert(b.fd == -1);
  phomemo_bridge_close(&b);
}

int
main(void)
{
  test_event_then_reply();
  test_error_reply();
  test_payload();
  test_reply_arrives_in_pieces();
  test_eof_is_an_error();
  test_abort_reply_is_skipped();
  test_reply_ticks_while_waiting();
  test_connect_missing_socket();
  puts("test_bridge: ok");
  return 0;
}
