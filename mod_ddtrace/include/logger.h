#pragma once

#include "http_log.h"
#include "httpd.h"

#include <datadog/logger.h>

#include <sstream>

class HttpdLogger final : public datadog::tracing::Logger {
  server_rec *svr_;
  int module_index_;
  std::mutex mutex_;
  std::ostringstream stream_;

public:
  HttpdLogger(server_rec *s, int module_index)
      : svr_(s), module_index_(module_index){};
  inline void log_error(const LogFunc &func) override { log(APLOG_ERR, func); }
  inline void log_startup(const LogFunc &func) override {
    log(APLOG_INFO, func);
  }

private:
  void log(char level, const LogFunc &func) {
    std::lock_guard<std::mutex> lock(mutex_);
    stream_.clear();
    stream_.str("");

    func(stream_);
    stream_ << '\n';

    ap_log_error(__FILE__, __LINE__, module_index_, level, 0, svr_, "%s",
                 stream_.str().c_str());
  }
};
