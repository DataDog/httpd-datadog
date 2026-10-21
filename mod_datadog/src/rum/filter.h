#pragma once

#include "httpd.h"
#include "injectbrowsersdk.h"

enum class InjectionState : char { init, pending, error, done };

struct rum_filter_ctx final {
  Snippet* snippet = nullptr;
  Injector* injector = nullptr;
  InjectionState state = InjectionState::init;
};

// Output Filter for injecting the RUM SDK
int rum_output_filter(ap_filter_t* filter, apr_bucket_brigade* brigade);
