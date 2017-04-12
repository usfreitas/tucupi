CC=gcc
CFLAGS=-O2 -Wall




all: tucupi_md5


tucupi_md5: tucupi_md5.c
	$(CC) -o $@ $^ $(CFLAGS)
