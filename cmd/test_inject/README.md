# test_inject command

Command line application to test the injection of a browser sdk snippet into an HTML document. The
output document containing the injected snippet is written to stdout.

## Example usage

```bash
cd cmd/test_inject
cargo run document.html
```

You can see the diff with the original document by doing something like:

```bash
diff -u document.html <(cargo run document.html)
```
