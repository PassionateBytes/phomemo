# This file is part of phomemo-printer-app.
# Copyright (C) 2026 Paul Bütof, Passionate Bytes Solutions
#
# phomemo-printer-app is free software: you can redistribute it and/or modify
# it under the terms of the GNU General Public License as published by
# the Free Software Foundation, either version 3 of the License, or
# (at your option) any later version.
#
# phomemo-printer-app is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
# GNU General Public License for more details.
#
# You should have received a copy of the GNU General Public License
# along with phomemo-printer-app.  If not, see <https://www.gnu.org/licenses/>.

# Build the Phomemo printer application against the system PAPPL.
#
#   make            build phomemo-printer-app
#   make test       build and run the C unit tests
#   make install    install the binary, the system unit and its preset
#                   (PREFIX=/usr/local, UNITDIR=/etc/systemd/system; needs
#                   root; DESTDIR for package builds)

PREFIX    ?= /usr/local
DESTDIR   ?=
UNITDIR   ?= /etc/systemd/system
PRESETDIR ?= /usr/lib/systemd/system-preset
CC        ?= cc
CFLAGS    ?= -O2 -g
ALL_CFLAGS = $(CFLAGS) -std=c99 -D_GNU_SOURCE -Wall -Wextra -Werror \
             -Wno-unused-parameter -I. -Ithird_party \
             $(shell pkg-config --cflags pappl) \
             -DPAPPL_VERSION_STR='"$(shell pkg-config --modversion pappl)"'
ALL_LDLIBS = $(LDLIBS) $(shell pkg-config --libs pappl) -pthread

APP      = phomemo-printer-app
SRCS     = main.c bridge.c device.c driver.c job.c icons.c
ICONS    = icons/m08f-48.png icons/m08f-128.png icons/m08f-512.png
VENDOR   = third_party/cJSON.c
VOBJS    = $(VENDOR:.c=.o)
OBJS     = $(SRCS:.c=.o)
TESTS    = tests/test_bridge tests/test_driver

all: $(APP)

$(APP): $(OBJS) $(VOBJS)
	$(CC) $(ALL_CFLAGS) $(LDFLAGS) -o $@ $(OBJS) $(VOBJS) $(ALL_LDLIBS)

%.o: %.c phomemo.h bridge.h
	$(CC) $(ALL_CFLAGS) -c -o $@ $<

icons.c: $(ICONS) icons/embed.sh
	sh icons/embed.sh $(ICONS) > $@

third_party/%.o: third_party/%.c
	$(CC) $(ALL_CFLAGS) -Wno-error -c -o $@ $<

tests/test_bridge: tests/test_bridge.o bridge.o $(VOBJS)
	$(CC) $(ALL_CFLAGS) $(LDFLAGS) -o $@ $^

tests/test_driver: tests/test_driver.o driver.o job.o device.o bridge.o icons.o $(VOBJS)
	$(CC) $(ALL_CFLAGS) $(LDFLAGS) -o $@ $^ $(ALL_LDLIBS)

test: $(TESTS)
	@for t in $(TESTS); do echo "== $$t"; ./$$t || exit 1; done

UNIT     = ../../packaging/systemd/phomemo-printer-app.service
PRESET   = ../../packaging/systemd/90-phomemo-printer-app.preset

# Installs the binary under PREFIX and the system unit (its ExecStart
# rewritten to that PREFIX) and preset; DESTDIR for package builds.
install: $(APP)
	install -d $(DESTDIR)$(PREFIX)/bin $(DESTDIR)$(UNITDIR) $(DESTDIR)$(PRESETDIR)
	install -m 755 $(APP) $(DESTDIR)$(PREFIX)/bin/$(APP)
	sed 's|/usr/bin/phomemo-printer-app|$(PREFIX)/bin/phomemo-printer-app|' $(UNIT) \
	  > $(DESTDIR)$(UNITDIR)/phomemo-printer-app.service
	install -m 644 $(PRESET) $(DESTDIR)$(PRESETDIR)/90-phomemo-printer-app.preset

clean:
	rm -f $(APP) $(OBJS) $(TESTS) tests/*.o third_party/*.o icons.c

.PHONY: all test install clean
