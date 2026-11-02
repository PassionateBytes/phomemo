# Build the Phomemo printer application against the system PAPPL.
#
#   make            build phomemo-printer-app
#   make test       build and run the C unit tests
#   make install    install under $(PREFIX) (default ~/.local)

PREFIX  ?= $(HOME)/.local
CC      ?= cc
CFLAGS  ?= -O2 -g
CFLAGS  += -std=c99 -D_GNU_SOURCE -Wall -Wextra -Werror -Wno-unused-parameter \
           -I. -Ithird_party $(shell pkg-config --cflags pappl)
LDLIBS  += $(shell pkg-config --libs pappl)

APP      = phomemo-printer-app
SRCS     = main.c bridge.c device.c driver.c job.c
VENDOR   = third_party/cJSON.c
VOBJS    = $(VENDOR:.c=.o)
OBJS     = $(SRCS:.c=.o)
TESTS    = tests/test_bridge tests/test_driver

all: $(APP)

$(APP): $(OBJS) $(VOBJS)
	$(CC) $(CFLAGS) -o $@ $(OBJS) $(VOBJS) $(LDLIBS)

%.o: %.c phomemo.h bridge.h
	$(CC) $(CFLAGS) -c -o $@ $<

third_party/%.o: third_party/%.c
	$(CC) $(CFLAGS) -Wno-error -c -o $@ $<

tests/test_bridge: tests/test_bridge.o bridge.o $(VOBJS)
	$(CC) $(CFLAGS) -o $@ $^

tests/test_driver: tests/test_driver.o driver.o job.o
	$(CC) $(CFLAGS) -o $@ $^ $(LDLIBS)

test: $(TESTS)
	@for t in $(TESTS); do echo "== $$t"; ./$$t || exit 1; done

install: $(APP)
	install -d $(PREFIX)/bin
	install -m 755 $(APP) $(PREFIX)/bin/$(APP)

clean:
	rm -f $(APP) $(OBJS) $(TESTS) tests/*.o third_party/*.o

.PHONY: all test install clean
