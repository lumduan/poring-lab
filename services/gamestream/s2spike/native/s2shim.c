// S2 spike: fixed-argument bridges for moonlight-common-c callbacks that ctypes cannot implement.
// CONNECTION_LISTENER_CALLBACKS.logMessage is variadic (printf-style); a ctypes callback can't take
// `...`, so the library calls s2_log_message, which formats the line and hands it to a plain
// `void (*)(const char*)` sink set from Python. Built in the gamestream image's builder stage.
#include <stdarg.h>
#include <stdio.h>

typedef void (*s2_log_sink_t)(const char *line);
static s2_log_sink_t s2_sink;

void s2_set_log_sink(s2_log_sink_t sink) { s2_sink = sink; }

void s2_log_message(const char *format, ...) {
    char line[1024];
    va_list ap;
    va_start(ap, format);
    vsnprintf(line, sizeof line, format, ap);
    va_end(ap);
    if (s2_sink) s2_sink(line);
}
