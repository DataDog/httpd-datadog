#include "crash-tracker/hook.h"

#include <http_log.h>
#include <http_protocol.h>
#include <http_request.h>
#include <libunwind.h>
#include <unistd.h>

#include <fstream>

// TODO: only avail for DEBUG build
int on_crash_handler(request_rec* r) {
  /*ap_log_rerror(APLOG_MARK, APLOG_WARNING, 0, r,*/
  /*              "connection is about to crash");*/

  ap_set_content_type(r, "text/plain");
  ap_rprintf(r, "Crashing in process %" APR_PID_T_FMT "...\n", getpid());
  ap_rflush(r);
  apr_sleep(apr_time_msec(500));

  *(int*)0xdeadbeef = 0xcafebabe;
  return OK;
}

int on_fatal_exception(ap_exception_info_t* ei) {
  std::ofstream file("/Users/damien.mehala/workspace/httpd-datadog/crash.txt");
  file << "sig: " << ei->sig << "\n";
  file << "pid: " << ei->pid << "\n";

  unw_context_t ctx;
  unw_getcontext(&ctx);
  unw_cursor_t cursor;
  unw_init_local(&cursor, &ctx);

  // Loop through the stack frames
  while (unw_step(&cursor) > 0) {
    unw_word_t offset, pc, sp;
    char function_name[256];

    // Get the program counter (PC)
    if (unw_get_reg(&cursor, UNW_REG_IP, &pc) != 0) {
      break;
    }

    unw_get_reg(&cursor, UNW_REG_SP, &sp);

    // Get the function name and offset
    if (unw_get_proc_name(&cursor, function_name, sizeof(function_name),
                          &offset) == 0) {
      file << "0x" << (long)pc << ", SP: 0x" << (long)sp << " : ("
           << function_name << "+0x" << (long)offset << ")\n";
    } else {
      file << "0x" << (long)pc << ", SP: 0x:" << (long)sp << "\n";
    }
  }

  file.close();
  return 0;
}
