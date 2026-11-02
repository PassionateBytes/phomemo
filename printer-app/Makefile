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
SRCS     = main.c
OBJS     = $(SRCS:.c=.o)
TESTS    =

all: $(APP)

$(APP): $(OBJS)
	$(CC) $(CFLAGS) -o $@ $(OBJS) $(LDLIBS)

%.o: %.c phomemo.h
	$(CC) $(CFLAGS) -c -o $@ $<

test: $(TESTS)
	@for t in $(TESTS); do echo "== $$t"; ./$$t || exit 1; done

install: $(APP)
	install -d $(PREFIX)/bin
	install -m 755 $(APP) $(PREFIX)/bin/$(APP)

clean:
	rm -f $(APP) $(OBJS) $(TESTS) tests/*.o third_party/*.o

.PHONY: all test install clean
