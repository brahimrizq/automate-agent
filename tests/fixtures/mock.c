/* Original synthetic process fixture. No ConnectWise code or protocol. */
#include <fcntl.h>
#include <netdb.h>
#include <signal.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <sys/socket.h>
#include <sys/stat.h>
#include <time.h>
#include <unistd.h>

static volatile sig_atomic_t running = 1;
static void stop(int number) { (void)number; running = 0; }
static void write_text(const char *path, const char *text) {
    FILE *f = fopen(path, "w");
    if (f) { fputs(text, f); fclose(f); }
}
static void check_network(const char *host) {
    struct addrinfo hints = {0}, *answer = NULL;
    hints.ai_socktype = SOCK_STREAM;
    int ok = 0;
    if (getaddrinfo(host, "8080", &hints, &answer) == 0) {
        for (struct addrinfo *p = answer; p; p = p->ai_next) {
            int fd = socket(p->ai_family, p->ai_socktype, p->ai_protocol);
            if (fd < 0) continue;
            struct timeval timeout = {1, 0};
            setsockopt(fd, SOL_SOCKET, SO_SNDTIMEO, &timeout, sizeof(timeout));
            ok = connect(fd, p->ai_addr, p->ai_addrlen) == 0;
            close(fd);
            if (ok) break;
        }
        freeaddrinfo(answer);
    }
    write_text("mock-network", ok ? "online" : "offline");
}
int main(void) {
    signal(SIGTERM, stop);
    signal(SIGINT, stop);
    int fd = open("state", O_CREAT | O_EXCL | O_WRONLY, 0600);
    if (fd >= 0) {
        unsigned long random_value = 0;
        FILE *random = fopen("/dev/urandom", "r");
        if (!random || fread(&random_value, sizeof(random_value), 1, random) != 1) return 2;
        fclose(random);
        dprintf(fd, "{\"computer_id\":\"%lx\",\"computer_password\":\"synthetic-private-state\"}", random_value);
        close(fd);
        write_text("mock-registrations", "1");
    }
    const char *mode = getenv("MOCK_MODE");
    const char *host = getenv("MOCK_HOST");
    int count = 0;
    while (running) {
        write_text("mock-heartbeat", "alive");
        if (host) check_network(host);
        if (mode && strcmp(mode, "crash") == 0 && ++count > 4) return 42;
        if (mode && strcmp(mode, "logs") == 0) {
            for (int i = 0; i < 3000; i++) puts("system_password synthetic-enrollment");
            fflush(stdout);
            FILE *log = fopen("agent.log", "a");
            if (log) { for (int i = 0; i < 30000; i++) fputs("synthetic native diagnostics\n", log); fclose(log); }
        }
        struct timespec delay = {0, 100000000};
        nanosleep(&delay, NULL);
    }
    write_text("mock-stopped", "graceful");
    return 0;
}
