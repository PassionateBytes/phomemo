# Build the Phomemo printer application against the system PAPPL.
#
#   make            build phomemo-printer-app
#   make test       build and run the C unit tests
#   make install    install under $(PREFIX) (default ~/.local); with a
#                   PREFIX inside $(HOME) the user unit goes to
#                   ~/.config/systemd/user as well

PREFIX  ?= $(HOME)/.local
CC      ?= cc
CFLAGS  ?= -O2 -g
CFLAGS  += -std=c99 -D_GNU_SOURCE -Wall -Wextra -Werror -Wno-unused-parameter \
           -I. -Ithird_party $(shell pkg-config --cflags pappl) \
           -DPAPPL_VERSION_STR='"$(shell pkg-config --modversion pappl)"'
LDLIBS  += $(shell pkg-config --libs pappl)

APP      = phomemo-printer-app
SRCS     = main.c bridge.c device.c driver.c job.c icons.c
ICONS    = icons/m08f-48.png icons/m08f-128.png icons/m08f-512.png
VENDOR   = third_party/cJSON.c
VOBJS    = $(VENDOR:.c=.o)
OBJS     = $(SRCS:.c=.o)
TESTS    = tests/test_bridge tests/test_driver

all: $(APP)

$(APP): $(OBJS) $(VOBJS)
	$(CC) $(CFLAGS) -o $@ $(OBJS) $(VOBJS) $(LDLIBS)

%.o: %.c phomemo.h bridge.h
	$(CC) $(CFLAGS) -c -o $@ $<

icons.c: $(ICONS) icons/embed.sh
	sh icons/embed.sh $(ICONS) > $@

third_party/%.o: third_party/%.c
	$(CC) $(CFLAGS) -Wno-error -c -o $@ $<

tests/test_bridge: tests/test_bridge.o bridge.o $(VOBJS)
	$(CC) $(CFLAGS) -o $@ $^

tests/test_driver: tests/test_driver.o driver.o job.o device.o bridge.o icons.o $(VOBJS)
	$(CC) $(CFLAGS) -o $@ $^ $(LDLIBS)

test: $(TESTS)
	@for t in $(TESTS); do echo "== $$t"; ./$$t || exit 1; done

UNIT     = ../packaging/phomemo-printer-app.service
UNITDIR  = $(HOME)/.config/systemd/user

install: $(APP)
	install -d $(PREFIX)/bin
	install -m 755 $(APP) $(PREFIX)/bin/$(APP)
	@case "$(PREFIX)" in \
	  $(HOME)/*) install -d $(UNITDIR); install -m 644 $(UNIT) $(UNITDIR)/; \
	    echo "installed $(UNITDIR)/phomemo-printer-app.service";; \
	  *) echo "user unit not installed; copy $(UNIT) to the systemd unit directory";; \
	esac

clean:
	rm -f $(APP) $(OBJS) $(TESTS) tests/*.o third_party/*.o icons.c

.PHONY: all test install clean
