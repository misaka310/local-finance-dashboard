#!/bin/bash
set -euxo pipefail
pip3 install .
for fuzzer in fuzz/*_fuzzer.py; do
  name=$(basename "$fuzzer" .py)
  package="${name}.pkg"
  pyinstaller --distpath "$OUT" --onefile --name "$package" "$fuzzer"
  cat > "$OUT/$name" <<EOF
#!/bin/sh
# LLVMFuzzerTestOneInput marker used by ClusterFuzzLite target discovery.
this_dir=\$(dirname "\$0")
exec "\$this_dir/$package" "\$@"
EOF
  chmod +x "$OUT/$name"
done
