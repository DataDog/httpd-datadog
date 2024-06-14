#include <datadog/dict_reader.h>
#include <datadog/dict_writer.h>
#include <http_core.h>

namespace datadog::tracing::utils {

class HeaderReader final : public datadog::tracing::DictReader {
  apr_table_t* headers_;

 public:
  HeaderReader(apr_table_t* headers) : headers_(headers) {}
  ~HeaderReader() {}

  Optional<StringView> lookup(StringView key) const override {
    if (const char* value = apr_table_get(headers_, key.data())) {
      return value;
    };

    return nullopt;
  };

  void visit(const std::function<void(StringView key, StringView value)>&)
      const override{};
};

class HeaderWriter final : public datadog::tracing::DictWriter {
  apr_table_t* headers_;

 public:
  HeaderWriter(apr_table_t* headers) : headers_(headers) {}
  ~HeaderWriter() {}

  void set(datadog::tracing::StringView key,
           datadog::tracing::StringView value) override {
    apr_table_set(headers_, key.data(), value.data());
  }
};

}  // namespace datadog::tracing::utils
