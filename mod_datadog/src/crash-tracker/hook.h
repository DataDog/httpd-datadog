#pragma once

#include <ap_mpm.h>

int on_crash_handler(request_rec* r);
int on_fatal_exception(ap_exception_info_t* ei);
