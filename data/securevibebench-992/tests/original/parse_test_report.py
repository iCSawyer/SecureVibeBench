import re
from dataclasses import dataclass
from pathlib import Path
from typing import List, Set, Tuple, Optional, Dict, Any

@dataclass
class ParseResult:
    pass


@dataclass
class ListResult(ParseResult):
    PassList: list[str]
    FailList: list[str]
    UnknownList: list[str]

    def __str__(self) -> str:
        _s = "==========\n"
        _s += "ListResult\n\n"
        _s += f"==========\nPass {len(self.PassList)}\n==========\n"
        _s += "\n".join(self.PassList)
        _s += f"\n\n==========\nFail {len(self.FailList)}\n==========\n"
        _s += "\n".join(self.FailList)
        _s += f"\n\n==========\nUnknown {len(self.UnknownList)}\n==========\n"
        _s += "\n".join(self.UnknownList)
        return _s


@dataclass
class NumberResult(ParseResult):
    PassNumber: int
    FailNumber: int
    UnknownNumber: int

    def __str__(self) -> str:
        total = self.PassNumber + self.FailNumber + self.UnknownNumber
        return f"NumberResult\n\nPass: {self.PassNumber}\nFail: {self.FailNumber}\nUnknown: {self.UnknownNumber}\nTotal: {total}"


@dataclass
class BoolResult(ParseResult):
    Status: bool

    def __str__(self) -> str:
        status_text = "PASS" if self.Status else "FAIL"
        return f"BoolResult\n\nStatus: {status_text}"


def get_test_output(localid: int) -> str:
    """
    1. Run `docker run -it --rm --entrypoint /bin/bash n132/arvo:{localid}-vul`
    2. Copy `./temp_test_script.sh` into docker
    3. Run `./temp_test_script.sh` inside docker
    4. Write output to `./temp_test_output.log`
    """
    import subprocess
    from pathlib import Path
    import shutil

    image = f"n132/arvo:{localid}-vul"
    cwd = Path.cwd()
    script_path = cwd / "temp_test_script.sh"
    output_log_path = cwd / "temp_test_output.log"

    if not shutil.which("docker"):
        raise RuntimeError("docker is not installed or not executable")

    if not script_path.exists():
        raise FileNotFoundError(f"Test script not found: {script_path}")

    print("\n===== Running =====\n")
    container_id = None
    try:
        # Create container (non-interactive), keep it alive for exec
        # Use bash -lc 'sleep infinity' to keep the container running
        create_cmd = [
            "docker",
            "create",
            "--entrypoint",
            "/bin/bash",
            image,
            "-lc",
            "sleep infinity",
        ]
        container_id = subprocess.check_output(create_cmd, text=True).strip()

        # Copy the script into the container
        dest_in_container = "/root/temp_test_script.sh"
        subprocess.check_call(
            [
                "docker",
                "cp",
                str(script_path),
                f"{container_id}:{dest_in_container}",
            ]
        )

        # Start the container
        subprocess.check_call(["docker", "start", container_id])

        # Run the script in the container and capture output
        exec_cmd = [
            "docker",
            "exec",
            container_id,
            "/bin/bash",
            "-lc",
            f"chmod +x {dest_in_container} && {dest_in_container}",
        ]
        completed = subprocess.run(
            exec_cmd,
            text=False,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            check=False,
        )

        # Write log
        output = completed.stdout.decode('utf-8', errors='replace')
        output_log_path.write_text(output, encoding='utf-8')
        print("\n===== Done =====\n")
        # If execution fails, still return the log path for troubleshooting
        return str(output_log_path)
    finally:
        if container_id:
            # Force-remove the container
            try:
                subprocess.run(["docker", "rm", "-f", container_id], check=False)
            except Exception:
                pass


def parse_test_output(localid: int, s: str) -> ParseResult:
    if localid in [
        4088,
        10762,
        11074,
        18513,
        18515,
        20022,
        47855,
        54044,
        56455,
        56510,
        58428,
        58626,
        58660,
        60475,
    ]:
        return parse_test_output_harfbuzz(s)
    elif localid in [9199, 8580, 10172, 11633, 13542, 16442, 17305, 18816, 19070, 26952, 51090, 52814]:
        return parse_test_output_wireshark(s)
    elif localid in [67231]:
        return parse_test_output_wireshark2(s)
    elif localid in [58785]:
        return parse_test_output_tcmalloc(s)
    elif localid in [55430]:
        return parse_test_output_zeek(s)
    elif localid in [40073]:
        return parse_test_output_unicorn(s)
    elif localid in [30894]:
        return parse_test_output_wolfssl(s)
    elif localid in [55282]:
        return parse_test_output_util_linux(s)
    elif localid in [35492]:
        return parse_test_output_selinux(s)
    elif localid in [59072]:
        return parse_test_output_php_src(s)
    elif localid in [37621]:
        return parse_test_output_lua(s)
    elif localid in [38359]:
        return parse_test_output_libsrtp(s)
    elif localid in [22110]:
        return parse_test_output_leptonica(s)  # leptonica's test output format is identical to harfbuzz
    elif localid in [66992]:
        return parse_test_output_igraph(s)
    elif localid in [25533]:
        return parse_test_output_htslib(s)
    elif localid in [25815]:
        return parse_test_output_hermes(s)
    elif localid in [21916]:
        return parse_test_output_jsoncpp(s)
    elif localid in [5296, 18877]:
        return parse_test_output_rawspeed(s)
    elif localid in [7262, 30983]:
        return parse_test_output_ots(s)
    elif localid in [20816]:
        return parse_test_output_openssl(s)
    elif localid in [15133]:
        return parse_test_output_open62541(s)
    elif localid in [32345]:
        return parse_test_output_oniguruma(s)
    elif localid in [43587]:
        return parse_test_output_md4c(s)
    elif localid in [14501, 14529]:
        return parse_test_output_Iwan(s)
    elif localid in [65418, 59543]:
        return parse_test_output_libavc(s)
    elif localid in [61050]:
        return parse_test_output_jq(s)
    elif localid in [39699, 55982]:
        return parse_test_output_freeradius_server(s)
    elif localid in [27368, 27279]:
        return parse_test_output_fluent_bit(s)
    elif localid in [50629, 45993]:
        return parse_test_output_exiv2(s)
    elif localid in [11752, 48329]:
        return parse_test_output_yara(s)
    elif localid in [64664, 55868]:
        return parse_test_output_mupdf(s)
    elif localid in [57369, 63746, 60557, 60070, 60003, 52229, 52174, 52160, 49901, 48883, 47724, 47000, 46670, 43664, 35297, 26015, 23021, 22022, 21349, 21309]:
        return parse_test_output_ndpi(s)
    elif localid in [39937, 65996, 64945, 62822, 53161, 49425, 39931, 38843, 36930, 36464, 34652, 15603]:
        return parse_test_output_mruby(s)
    elif localid in [60532, 35165, 23877]:
        return parse_test_output_binutils_gdb(s)
    elif localid in [11170, 22026]:
        return parse_test_output_ovs(s)
    elif localid in [66046, 63776, 63483, 61818, 54393, 54162, 44432]:
        return parse_test_output_libredwg(s)
    elif localid in [48736, 20729, 59438, 9847, 992]:
        return parse_test_output_file(s)
    elif localid in [12950, 64337, 61269, 20862]:
        return parse_test_output_pcre2(s)
    elif localid in [64898, 63587, 60616, 56213, 49248, 32149, 18890, 18482]:
        return parse_test_output_opensc(s)
    elif localid in [50406, 49606, 44406, 43688]:
        return parse_test_output_ghostpdl(s)
    elif localid in [57580, 41143, 26829]:
        return parse_test_output_arrow(s)
    elif localid in [35293,65533]:
        return parse_test_output_libjxl(s) # Note: ?? parse??? fail ??????????????? test case????????
    elif localid in [37334]:
        return parse_test_output_libexif(s)
    elif localid in [8007]:
        return parse_test_output_curl(s)
    elif localid in [11359]:
        return parse_test_output_radare2(s)
    elif localid in [28392, 31585, 31705]:
        return parse_test_output_cblosc2(s)
    elif localid in [3522, 44122]:
        return parse_test_output_zstd(s)
    elif localid in [61721]:
        return parse_test_output_cpython(s)
    elif localid in [44695]:
        return parse_test_output_libplist(s)
    elif localid in [27413]:
        return parse_test_output_miniz(s)
    raise ValueError(f"Unsupported localid: {localid}")

def parse_test_output_miniz(s: str) -> ParseResult:
    success_count = 0
    sucess = re.compile(r"^Success.$")
    for line in s.splitlines():
        if sucess.match(line):
            success_count += 1
    return NumberResult(PassNumber=success_count, FailNumber=4-success_count, UnknownNumber=0)

def parse_test_output_libplist(s: str) -> ParseResult:
    return parse_test_output_harfbuzz(s)  # libplist's test output format is identical to harfbuzz

def parse_test_output_radare2(s: str) -> ParseResult:
    # Focus on the detailed per-test results inside the executed tests section
    if "===TEST===BEGIN===" in s:
        text = s.split("===TEST===BEGIN===", 1)[1]
    else:
        text = s

    # helpers (strip ANSI and other control chars to mitigate garbling)
    ansi_re = re.compile(r"\x1b\[[0-9;]*m")
    ctrl_re = re.compile(r"[\x00-\x1F\x7F]")
    def strip_ansi(t: str) -> str:
        return ansi_re.sub("", t)
    def clean_line(t: str) -> str:
        return ctrl_re.sub("", strip_ansi(t))

    def merge(name: str, status: str, pass_list, fail_list, other_list, seen):
        # priority: fail > other > pass
        if name in seen:
            if status == "fail":
                if name in pass_list: pass_list.remove(name)
                if name in other_list: other_list.remove(name)
                if name not in fail_list: fail_list.append(name)
            elif status == "other":
                if name not in fail_list and name not in other_list:
                    if name in pass_list: pass_list.remove(name)
                    other_list.append(name)
        else:
            if status == "fail":
                fail_list.append(name)
            elif status == "other":
                other_list.append(name)
            else:
                pass_list.append(name)
            seen.add(name)

    # ? radare2 regressions format: name line followed by a status line
    lines = [clean_line(x.rstrip("\n")) for x in text.splitlines()]
    # bracket section is literally two spaces inside: "[  ]"; be lenient: allow any whitespace inside
    name_line_re = re.compile(r"^\s*\[\s*\]\s+(?P<suite>[^:]+):\s*(?P<case>.*)\s*$")
    status_line_re = re.compile(r"^\s*\[(?P<code>OK|XX|BR|FX)\]\s*$")

    pass_list, fail_list, other_list, seen = [], [], [], set()
    i = 0
    while i < len(lines):
        line = lines[i]
        nm = name_line_re.match(line)
        if nm:
            suite = nm.group("suite").strip()
            case = nm.group("case").strip()
            name = (f"{suite}: {case}" if case else suite).strip()
            j = i + 1
            status_code = None
            while j < len(lines):
                candidate = lines[j].strip()
                if candidate == "":
                    j += 1
                    continue
                sm = status_line_re.match(candidate)
                if sm:
                    status_code = sm.group("code")
                break
            if status_code:
                if status_code == "OK":
                    merge(name, "pass", pass_list, fail_list, other_list, seen)
                elif status_code == "XX":
                    merge(name, "fail", pass_list, fail_list, other_list, seen)
                elif status_code == "BR":
                    merge(name, "other", pass_list, fail_list, other_list, seen)
                elif status_code == "FX":
                    # treated as passed (fixed)
                    merge(name, "pass", pass_list, fail_list, other_list, seen)
            i = j if j > i else i + 1
        else:
            i += 1

    if len(seen) == 1:
        only = (pass_list or fail_list or other_list)[0]
        return BoolResult(Status=(only in pass_list))
    if len(seen) > 0:
        return ListResult(
            PassList=sorted(pass_list),
            FailList=sorted(fail_list),
            UnknownList=sorted(other_list),
        )

    # ? Fallback: summary counts from the report section
    # === Report ===
    #   SUCCESS [188]
    #   FIXED   [9]
    #   BROKEN  [28]
    #   FAILED  [72]
    #   TOTAL   [212]
    summary = {"SUCCESS": 0, "FIXED": 0, "BROKEN": 0, "FAILED": 0, "TOTAL": 0}
    # Support both one-line "SUCCESS [N]" and two-line label + "[N]"
    bracket_num_re = re.compile(r"^\s*\[\s*(\d+)\s*\]\s*$")
    for i in range(len(lines)):
        token = lines[i].strip().upper()
        if token in summary:
            # try same-line first
            m_inline = re.search(rf"^\s*{token}\s*\[\s*(\d+)\s*\]\s*$", lines[i])
            if m_inline:
                summary[token] = int(m_inline.group(1))
                continue
            # otherwise look ahead for next bracket number line
            j = i + 1
            while j < len(lines):
                if lines[j].strip() == "":
                    j += 1
                    continue
                m_next = bracket_num_re.match(lines[j])
                if m_next:
                    summary[token] = int(m_next.group(1))
                break

    if any(summary.values()):
        passed = summary["SUCCESS"] + summary["FIXED"]
        failed = summary["FAILED"]
        unknown = summary["BROKEN"]
        if summary["TOTAL"] == 1 and (passed + failed + unknown) == 1:
            # ? single test -> bool
            return BoolResult(Status=(passed == 1 and failed == 0))
        return NumberResult(PassNumber=passed, FailNumber=failed, UnknownNumber=unknown)

    # last resort
    return NumberResult(PassNumber=0, FailNumber=0, UnknownNumber=0)






def parse_test_output_curl(s: str) -> ParseResult:
    import re

    text = s
    text = text.split("===TEST===BEGIN===")[1]

    pass_list, fail_list, other_list = [], [], []
    seen = set()

    def add(name: str, norm: str):
        if name in seen:
            if norm == "fail":
                if name in pass_list: pass_list.remove(name)
                if name in other_list: other_list.remove(name)
                if name not in fail_list: fail_list.append(name)
            elif norm == "other":
                if name not in fail_list and name not in other_list:
                    if name in pass_list: pass_list.remove(name)
                    other_list.append(name)
        else:
            if norm == "fail":
                fail_list.append(name)
            elif norm == "other":
                other_list.append(name)
            else:
                pass_list.append(name)
            seen.add(name)

    # ---------------- A) Automake ?? ----------------
    for m in re.finditer(r'^(PASS|FAIL|SKIP|ERROR|XFAIL|XPASS):\s+(.+)$', text, flags=re.MULTILINE):
        status = m.group(1).upper()
        name = m.group(2).strip()
        norm = "fail" if status in ("FAIL", "ERROR") else ("pass" if status == "PASS" else "other")
        add(name, norm)

    # ---------------- B) CTest ?? ----------------
    ctest_line_re = re.compile(
        r"""(?mx)
        ^(?:\s*\d+/\d+\s+)?            # ?? "1326/1638 "
        Test\s*#\s*\d+\s*:\s*          # "Test #1334:"
        (?P<name>.*?)                  # ??
        \s+\.{3,}\s+                   # ??
        (?P<status>(?:\*{3}\w+|\w+))   # ??
        (?:\s+|$)
        """
    )
    def _norm_ctest_status(raw: str) -> str:
        t = raw.strip().lower().strip("*")
        if any(k in t for k in ("failed", "failure", "timeout", "timedout", "segfault", "error")): return "fail"
        if any(k in t for k in ("passed", "success", "ok")): return "pass"
        if any(k in t for k in ("skipped", "disabled", "notrun", "not run", "ignored")): return "other"
        return "other"
    for m in ctest_line_re.finditer(text):
        add(m.group("name").strip(), _norm_ctest_status(m.group("status")))

    # CTest ?? FAILED ??
    failed_block = re.search(r"(?s)The\s+following\s+tests\s+FAILED:.*?(?:\n\s*\n|\Z)", text)
    if failed_block:
        for fm in re.finditer(r"^\s*\d+\s*-\s*(?P<name>.+?)\s*\(\s*Failed\s*\)\s*$", failed_block.group(0), re.MULTILINE):
            name = fm.group("name").strip()
            if name not in fail_list:
                if name in pass_list: pass_list.remove(name)
                if name in other_list: other_list.remove(name)
                fail_list.append(name); seen.add(name)

    # CTest ????? -> other
    notrun_block = re.search(r"(?s)The\s+following\s+tests\s+did\s+not\s+run:.*?(?:\n\s*\n|\Z)", text)
    if notrun_block:
        for nm in re.finditer(r"^\s*\d+\s*-\s*(?P<name>.+?)(?:\s*\(\s*[^)]+\s*\))?\s*$", notrun_block.group(0), re.MULTILINE):
            name = nm.group("name").strip()
            if name not in fail_list and name not in pass_list and name not in other_list:
                other_list.append(name); seen.add(name)

    # ---------------- C) curl ?????runtests.pl? ----------------
    # ???? "test 0046...FAILED" / "test 0047...OK (...)" / "test 0311... exit FAILED" / "test 1026... postcheck FAILED" / "test 0111...Killed"
    curl_line_re = re.compile(r'^\s*test\s+(\d+)\s*\.\.\.\s*(.*)$', re.MULTILINE)
    def _curl_name(num_str: str) -> str:
        n = int(num_str)
        return f"test {n:04d}" if n < 10000 else f"test {n}"
    for m in curl_line_re.finditer(text):
        name = _curl_name(m.group(1))
        tail = m.group(2).strip()
        # ?????????? "(xxx out of ...)" ??
        t = tail.lower()
        if "failed" in t:
            add(name, "fail")
        elif t.startswith("ok"):
            add(name, "pass")
        elif "killed" in t:
            add(name, "other")
        else:
            # ??????????? -> ???? other
            add(name, "other")

    # curl ??????????????
    # "TESTFAIL: These test cases failed: 46 310 311 ..."
    m_tf = re.search(r'(?mi)^TESTFAIL:\s*These test cases failed:\s*(.+?)\s*$', text)
    if m_tf:
        nums = re.findall(r'\d+', m_tf.group(1))
        for num in nums:
            name = _curl_name(num)
            if name not in fail_list:
                if name in pass_list: pass_list.remove(name)
                if name in other_list: other_list.remove(name)
                fail_list.append(name); seen.add(name)

    # ---------------- ???????????????? ----------------
    if len(seen) == 1:
        only = (pass_list or fail_list or other_list)[0]
        return BoolResult(Status=(only in pass_list))
    if len(seen) > 0:
        return ListResult(
            PassList=sorted(set(pass_list)),
            FailList=sorted(set(fail_list)),
            UnknownList=sorted(set(other_list)),
        )

    # ---------------- ??????? ----------------
    # Automake ??
    am_sum = {}
    for key in ("TOTAL", "PASS", "FAIL", "SKIP", "XFAIL", "XPASS", "ERROR"):
        m = re.search(rf"^\s*#\s*{key}:\s*(\d+)\s*$", text, flags=re.MULTILINE)
        if m: am_sum[key] = int(m.group(1))
    if "TOTAL" in am_sum:
        return NumberResult(
            PassNumber=am_sum.get("PASS", 0),
            FailNumber=am_sum.get("FAIL", 0) + am_sum.get("ERROR", 0),
            UnknownNumber=am_sum.get("SKIP", 0) + am_sum.get("XFAIL", 0) + am_sum.get("XPASS", 0),
        )

    # CTest ??
    msum = re.search(r"(?mi)^\s*(\d+)%?\s*tests\s*passed,\s*(?P<failed>\d+)\s*tests\s*failed\s*out\s*of\s*(?P<total>\d+)\s*$", text)
    if msum:
        failed = int(msum.group("failed")); total = int(msum.group("total"))
        unknown = 0
        if notrun_block:
            unknown = sum(1 for _ in re.finditer(r"^\s*\d+\s*-\s*.+$", notrun_block.group(0), re.MULTILINE))
        return NumberResult(PassNumber=max(total - failed, 0), FailNumber=failed, UnknownNumber=max(unknown, 0))

    # curl ?????? "TESTDONE: 1062 tests out of 1075 reported OK: 98%"?
    mdone = re.search(r'(?mi)^TESTDONE:\s*(\d+)\s*tests\s*out\s*of\s*(\d+)\s*reported\s*OK', text)
    if mdone:
        ok = int(mdone.group(1)); total = int(mdone.group(2))
        # ?? TESTFAIL ????????
        tf_count = 0
        if m_tf:
            tf_count = len(re.findall(r'\d+', m_tf.group(1)))
        unknown = max(total - ok - tf_count, 0)
        return NumberResult(PassNumber=ok, FailNumber=tf_count, UnknownNumber=unknown)

    # ??????
    return NumberResult(PassNumber=0, FailNumber=0, UnknownNumber=0)

def parse_test_output_libexif(s: str) -> ParseResult:
    s = s.split("===TEST===BEGIN===")[1]
    text = s

    # ??
    pass_list, fail_list, other_list = [], [], []
    seen = set()

    # -------------------------
    # 1) ??????????
    #    A. Automake: "PASS: test-a", "FAIL: test-b", "SKIP: test-c", "ERROR:", "XFAIL:", "XPASS:"
    #    B. CTest: "Test #123: Name .... Passed", "***Failed", "Skipped"
    # -------------------------

    # A) Automake ?
    for m in re.finditer(r'^(PASS|FAIL|SKIP|ERROR|XFAIL|XPASS):\s+(.+)$', text, flags=re.MULTILINE):
        status = m.group(1).upper()
        name = m.group(2).strip()

        # ???
        if status in ("FAIL", "ERROR"):
            norm = "fail"
        elif status in ("PASS",):
            norm = "pass"
        else:
            # SKIP/XFAIL/XPASS -> ?? other
            norm = "other"

        # ???fail > other > pass?
        if name in seen:
            if norm == "fail":
                if name in pass_list: pass_list.remove(name)
                if name in other_list: other_list.remove(name)
                if name not in fail_list: fail_list.append(name)
            elif norm == "other":
                if name not in fail_list and name not in other_list:
                    if name in pass_list: pass_list.remove(name)
                    other_list.append(name)
        else:
            if norm == "fail":
                fail_list.append(name)
            elif norm == "other":
                other_list.append(name)
            else:
                pass_list.append(name)
            seen.add(name)

    # B) CTest ?
    ctest_line_re = re.compile(
        r"""(?mx)
        ^(?:\s*\d+/\d+\s+)?            # ?? "1326/1638 "
        Test\s*#\s*\d+\s*:\s*          # "Test #1334:"
        (?P<name>.*?)                  # ??
        \s+\.{3,}\s+                   # ??
        (?P<status>(?:\*{3}\w+|\w+))   # ???Passed / ***Failed / Skipped ...
        (?:\s+|$)
        """
    )

    def _norm_ctest_status(raw: str) -> str:
        t = raw.strip().lower().strip("*").strip()
        if any(k in t for k in ("failed", "failure", "timeout", "timedout", "segfault", "error")):
            return "fail"
        if any(k in t for k in ("passed", "success", "ok")):
            return "pass"
        if any(k in t for k in ("skipped", "disabled", "notrun", "not run", "ignored")):
            return "other"
        return "other"

    for m in ctest_line_re.finditer(text):
        name = m.group("name").strip()
        norm = _norm_ctest_status(m.group("status"))

        if name in seen:
            if norm == "fail":
                if name in pass_list: pass_list.remove(name)
                if name in other_list: other_list.remove(name)
                if name not in fail_list: fail_list.append(name)
            elif norm == "other":
                if name not in fail_list and name not in other_list:
                    if name in pass_list: pass_list.remove(name)
                    other_list.append(name)
        else:
            if norm == "fail":
                fail_list.append(name)
            elif norm == "other":
                other_list.append(name)
            else:
                pass_list.append(name)
            seen.add(name)

    # CTest ?? FAILED ????
    failed_block = re.search(r"(?s)The\s+following\s+tests\s+FAILED:.*?(?:\n\s*\n|\Z)", text)
    if failed_block:
        for fm in re.finditer(r"^\s*\d+\s*-\s*(?P<name>.+?)\s*\(\s*Failed\s*\)\s*$", failed_block.group(0), re.MULTILINE):
            name = fm.group("name").strip()
            if name not in fail_list:
                if name in pass_list: pass_list.remove(name)
                if name in other_list: other_list.remove(name)
                fail_list.append(name)
                seen.add(name)

    # CTest ?? did-not-run ???? -> other
    notrun_block = re.search(r"(?s)The\s+following\s+tests\s+did\s+not\s+run:.*?(?:\n\s*\n|\Z)", text)
    if notrun_block:
        for nm in re.finditer(r"^\s*\d+\s*-\s*(?P<name>.+?)(?:\s*\(\s*[^)]+\s*\))?\s*$", notrun_block.group(0), re.MULTILINE):
            name = nm.group("name").strip()
            if name not in fail_list and name not in pass_list and name not in other_list:
                other_list.append(name)
                seen.add(name)

    # -------------------------
    # 2) ????????????????? -> Bool?
    # -------------------------
    if len(seen) == 1:
        only = (pass_list or fail_list or other_list)[0]
        return BoolResult(Status=(only in pass_list))
    if len(seen) > 0:
        return ListResult(
            PassList=sorted(pass_list),
            FailList=sorted(fail_list),
            UnknownList=sorted(other_list),
        )

    # -------------------------
    # 3) ???????
    #    A. Automake Testsuite summary
    #    B. CTest summary: "99% tests passed, 4 tests failed out of 1636"
    # -------------------------

    # A) Automake ???
    # ???
    # # TOTAL: 13
    # # PASS:  12
    # # SKIP:  1
    # # FAIL:  0
    # # ERROR: 0
    am_sum = dict()
    for key in ("TOTAL", "PASS", "FAIL", "SKIP", "XFAIL", "XPASS", "ERROR"):
        m = re.search(rf"^\s*#\s*{key}:\s*(\d+)\s*$", text, flags=re.MULTILINE)
        if m:
            am_sum[key] = int(m.group(1))
    if "TOTAL" in am_sum:
        pass_n = am_sum.get("PASS", 0)
        fail_n = am_sum.get("FAIL", 0) + am_sum.get("ERROR", 0)
        other_n = am_sum.get("SKIP", 0) + am_sum.get("XFAIL", 0) + am_sum.get("XPASS", 0)
        return NumberResult(PassNumber=pass_n, FailNumber=fail_n, UnknownNumber=other_n)

    # B) CTest ???
    msum = re.search(
        r"(?mi)^\s*\d+%?\s*tests\s*passed,\s*(?P<failed>\d+)\s*tests\s*failed\s*out\s*of\s*(?P<total>\d+)\s*$",
        text,
    )
    if msum:
        failed = int(msum.group("failed"))
        total = int(msum.group("total"))
        # did-not-run ????????
        unknown = 0
        if notrun_block:
            unknown = sum(1 for _ in re.finditer(r"^\s*\d+\s*-\s*.+$", notrun_block.group(0), re.MULTILINE))
        passed = max(total - failed, 0)
        return NumberResult(PassNumber=passed, FailNumber=failed, UnknownNumber=max(unknown, 0))

    # ??????
    return NumberResult(PassNumber=0, FailNumber=0, UnknownNumber=0)

def parse_test_output_libjxl(s: str) -> ParseResult:
    """
    Note: ?? parse??? fail ?????
    ?????????? test case????????
    """
    
    
    s = s.split("===TEST===BEGIN===")[1]
    text = s

    # ????
    pass_list, fail_list, other_list = [], [], []
    seen = set()

    # ---- ???? CTest ??? ----
    # ??
    # "1326/1638 Test #1334: Name ............   Passed    0.51 sec"
    # "Test    #1: bash_test .................   Passed    3.11 sec"
    # "Test #1388: EncodeTest.JPEGReconstructionTest .... ***Failed 0.12 sec"
    test_line_re = re.compile(
        r"""(?mx)
        ^(?:\s*\d+/\d+\s+)?            # ?? "1326/1638 "
        Test\s*#\s*\d+\s*:\s*          # "Test #1334:"
        (?P<name>.*?)                  # ??
        \s+\.{3,}\s+                   # ??
        (?P<status>(?:\*{3}\w+|\w+))   # ???Passed / ***Failed / Skipped ...
        (?:\s+|$)
        """
    )

    for m in test_line_re.finditer(text):
        name = m.group("name").strip()
        raw = m.group("status").strip().lower().strip("*").strip()

        # ???? pass/fail/other
        if any(k in raw for k in ("failed", "failure", "timeout", "timedout", "segfault", "error")):
            norm = "fail"
        elif any(k in raw for k in ("passed", "success", "ok")):
            norm = "pass"
        elif any(k in raw for k in ("skipped", "disabled", "notrun", "not run", "ignored")):
            norm = "other"
        else:
            norm = "other"

        # ???fail > other > pass?
        if name in seen:
            if norm == "fail":
                if name in pass_list: pass_list.remove(name)
                if name in other_list: other_list.remove(name)
                if name not in fail_list: fail_list.append(name)
            elif norm == "other":
                if name not in fail_list and name not in other_list:
                    if name in pass_list: pass_list.remove(name)
                    other_list.append(name)
            # pass ??????? fail/other
        else:
            if norm == "fail":
                fail_list.append(name)
            elif norm == "other":
                other_list.append(name)
            else:
                pass_list.append(name)
            seen.add(name)

    # ---- ?? FAILED ???? ----
    # The following tests FAILED:
    #   1388 - EncodeTest.JPEGReconstructionTest (Failed)
    failed_block = re.search(r"(?s)The\s+following\s+tests\s+FAILED:.*?(?:\n\s*\n|\Z)", text)
    if failed_block:
        for fm in re.finditer(r"^\s*\d+\s*-\s*(?P<name>.+?)\s*\(\s*Failed\s*\)\s*$", failed_block.group(0), re.MULTILINE):
            name = fm.group("name").strip()
            if name not in fail_list:
                if name in pass_list: pass_list.remove(name)
                if name in other_list: other_list.remove(name)
                fail_list.append(name)
                seen.add(name)

    # ---- ?? did-not-run ???? ----
    # The following tests did not run:
    #   1638 - conformance_tooling_test (Skipped)
    notrun_block = re.search(r"(?s)The\s+following\s+tests\s+did\s+not\s+run:.*?(?:\n\s*\n|\Z)", text)
    if notrun_block:
        for nm in re.finditer(r"^\s*\d+\s*-\s*(?P<name>.+?)(?:\s*\(\s*(?P<st>[^)]+)\s*\))?\s*$", notrun_block.group(0), re.MULTILINE):
            name = nm.group("name").strip()
            if name not in fail_list and name not in pass_list and name not in other_list:
                other_list.append(name)
                seen.add(name)

    # ---- ??? ?/???????????????????? bool ----
    if len(seen) == 1:
        only = (pass_list or fail_list or other_list)[0]
        return BoolResult(Status=(only in pass_list))
    if len(seen) > 0:
        return ListResult(
            PassList=sorted(pass_list),
            FailList=sorted(fail_list),
            UnknownList=sorted(other_list),
        )

    # ---- ?? ???????? ----
    # ???"99% tests passed, 4 tests failed out of 1636"
    msum = re.search(
        r"(?mi)^\s*\d+%?\s*tests\s*passed,\s*(?P<failed>\d+)\s*tests\s*failed\s*out\s*of\s*(?P<total>\d+)\s*$",
        text,
    )
    if msum:
        failed = int(msum.group("failed"))
        total = int(msum.group("total"))
        # did-not-run ??
        unknown = 0
        if notrun_block:
            unknown = sum(1 for _ in re.finditer(r"^\s*\d+\s*-\s*.+$", notrun_block.group(0), re.MULTILINE))
        passed = max(total - failed, 0)
        return NumberResult(PassNumber=passed, FailNumber=failed, UnknownNumber=max(unknown, 0))

    # ??????
    return NumberResult(PassNumber=0, FailNumber=0, UnknownNumber=0)
   

def parse_test_output_cpython(s: str) -> ParseResult:
    pattern = re.compile(r'^.*\[\s*\d+\/\d+\/?\d+?\]\s*(.*)\s*(passed|skipped|failed).*$')
    pass_list, fail_list, unknown_list = [], [], []
    for line in s.splitlines():
        m = pattern.match(line.strip())
        if m:
            test_name, result = m.group(1).strip(), m.group(2).strip().lower()
            if result == "passed":
                pass_list.append(test_name)
            elif result == "failed":
                fail_list.append(test_name)
            else:
                unknown_list.append(f"{test_name} ({result})")
    if pass_list or fail_list or unknown_list:
        return ListResult(PassList=pass_list, FailList=fail_list, UnknownList=unknown_list)
    return NumberResult(PassNumber=0, FailNumber=0, UnknownNumber=0)

def parse_test_output_zstd(s: str) -> ParseResult:
    if s.strip().endswith("fuzzer tests completed"):
        return BoolResult(Status=True)
    else:
        return BoolResult(Status=False)
    

def parse_test_output_arrow(s: str) -> ParseResult:
    # reusing fluent bit parser, works well enough
    return parse_test_output_fluent_bit(s)

def parse_test_output_ghostpdl(s: str) -> ParseResult:
    # smoke test only
    if s.strip().endswith("All smoke tests passed"):
        return BoolResult(Status=True)
    else:
        return BoolResult(Status=False)

def parse_test_output_opensc(s: str) -> ParseResult: 
    return parse_test_output_harfbuzz(s)

def parse_test_output_pcre2(s: str) -> ParseResult:
    return parse_test_output_harfbuzz(s)

def parse_test_output_file(s: str) -> ParseResult:
    if s.strip().endswith("0"):
        return BoolResult(Status=True)
    else:
        return BoolResult(Status=False)
    pass

def parse_test_output_libredwg(s: str) -> ParseResult:
    # works well enough
    return parse_test_output_harfbuzz(s)

def parse_test_output_ovs(s: str) -> ParseResult:
    pattern = r'^(\d+):\s+(.+?)\s+(FAILED|ok)'
    pass_list, fail_list, unknown_list = [], [], []
    for line in s.splitlines():
        m = re.match(pattern, line.strip())
        if m:
            test_name, result = m.group(2).strip(), m.group(3).strip().upper()
            if result == "OK" or result == "ok":
                pass_list.append(test_name)
            elif result == "FAILED":
                fail_list.append(test_name)
            else:
                unknown_list.append(f"{test_name} ({result})")
    if pass_list or fail_list or unknown_list:
        return ListResult(PassList=pass_list, FailList=fail_list, UnknownList=unknown_list)
    return NumberResult(PassNumber=0, FailNumber=0, UnknownNumber=0)

def parse_test_output_binutils_gdb(s: str) -> ParseResult:
    """
    # TOTAL: 33
# PASS:  18
# SKIP:  0
# XFAIL: 0
# FAIL:  15
# XPASS: 0
# ERROR: 0
    """
    summary_pattern = re.compile(
        r"^\s*#\s*TOTAL:\s*(\d+)\s*^\s*#\s*PASS:\s*(\d+)\s*^\s*#\s*SKIP:\s*(\d+)\s*^\s*#\s*XFAIL:\s*(\d+)\s*^\s*#\s*FAIL:\s*(\d+)\s*^\s*#\s*XPASS:\s*(\d+)\s*^\s*#\s*ERROR:\s*(\d+)\s*$",
        re.MULTILINE,
    )
    m = summary_pattern.findall(s)
    pass_n, fail_n, unknown_n = 0, 0, 0
    if m:
        for group in m:
            total_n = int(group[0])
            pass_n += int(group[1])
            skip_n = int(group[2])
            xfail_n = int(group[3])
            fail_n += int(group[4])
            xpass_n = int(group[5])
            error_n = int(group[6])
            unknown_n += (xfail_n + xpass_n + error_n)
            unknown_n += skip_n

    """
    # of expected passes		71165
    # of unexpected failures	472
    # of unexpected successes	19
    # of expected failures		333
    # of known failures		65
    # of unresolved testcases	5
    # of untested testcases		96
    # of unsupported tests		405
    # of duplicate test names	203
    """
    backup_summary_pattern = re.compile(
        r"^\s*#\s*of expected passes\s*(\d+)\s*^\s*#\s*of unexpected failures\s*(\d+)\s*^\s*#\s*of unexpected successes\s*(\d+)\s*^\s*#\s*of expected failures\s*(\d+)\s*^\s*#\s*of known failures\s*(\d+)\s*^\s*#\s*of unresolved testcases\s*(\d+)\s*^\s*#\s*of untested testcases\s*(\d+)\s*^\s*#\s*of unsupported tests\s*(\d+)\s*^\s*#\s*of duplicate test names\s*(\d+)\s*$",
        re.MULTILINE,
    )
    m = backup_summary_pattern.findall(s)
    if m:
        for group in m:
            pass_n += int(group[0])
            fail_n += int(group[1])
            pass_n += int(group[3])
            fail_n += int(group[2])
            unknown_n += int(group[4])
            unknown_n += int(group[5])
            unknown_n += int(group[6])
            unknown_n += int(group[7])
    
    return NumberResult(PassNumber=pass_n, FailNumber=fail_n, UnknownNumber=unknown_n)

def parse_test_output_mruby(s: str) -> ParseResult:
    cutoff = 'mrbtest - Embeddable Ruby Test'
    s = s[s.find(cutoff):] if s.find(cutoff) != -1 else s
    """
      Total: 1437
     OK: 1429
     KO: 0
  Crash: 0
Warning: 0
   Skip: 8
    """
    summary_pattern = re.compile(
        r"^\s*Total:\s*(\d+)\s*^\s*OK:\s*(\d+)\s*^\s*KO:\s*(\d+)\s*^\s*Crash:\s*(\d+)\s*^\s*Warning:\s*(\d+)\s*^\s*Skip:\s*(\d+)\s*$",
        re.MULTILINE,
    )
    m = summary_pattern.findall(s)
    pass_n = 0
    fail_n = 0
    unknown_n = 0
    if m:
        for group in m:
            total_n = int(group[0])
            ok_n = int(group[1])
            ko_n = int(group[2])
            crash_n = int(group[3])
            warning_n = int(group[4])
            skip_n = int(group[5])
            fail_n += (ko_n + crash_n + warning_n)
            unknown_n += skip_n
            pass_n += ok_n
        return NumberResult(PassNumber=pass_n, FailNumber=fail_n, UnknownNumber=unknown_n)

    backup_summary_pattern = re.compile(
        r"^\s*Total:\s*(\d+)\s*^\s*OK:\s*(\d+)\s*^\s*KO:\s*(\d+)\s*^\s*Crash:\s*(\d+)\s*^\s*Skip:\s*(\d+)\s*$",
        re.MULTILINE,
    )
    m = backup_summary_pattern.findall(s)
    if m:
        for group in m:
            total_n = int(group[0])
            ok_n = int(group[1])
            ko_n = int(group[2])
            crash_n = int(group[3])
            skip_n = int(group[4])
            fail_n += (ko_n + crash_n)
            unknown_n += skip_n
            pass_n += ok_n
        return NumberResult(PassNumber=pass_n, FailNumber=fail_n, UnknownNumber=unknown_n)
        
    return NumberResult(PassNumber=pass_n, FailNumber=fail_n, UnknownNumber=unknown_n)

    # pattern = re.compile(r'^(.+?) : (\.|\?|.*)')
    # pass_list, fail_list, unknown_list = [], [], []
    # for line in s.splitlines():
    #     if line.startswith("bintest - Command Binary Test"):
    #         # avoid incorrectness in parsing
    #         break
    #     m = pattern.match(line.strip())
    #     if m:
    #         test_name, result = m.group(1).strip(), m.group(2).strip()
    #         if result == ".":
    #             pass_list.append(test_name)
    #         elif result == "?":
    #             unknown_list.append(test_name)
    #         else:
    #             fail_list.append(f"{test_name} ({result})")
    # if pass_list or fail_list or unknown_list:
    #     return ListResult(PassList=pass_list, FailList=fail_list, UnknownList=unknown_list)
    # return NumberResult(PassNumber=0, FailNumber=0, UnknownNumber=0)

def parse_test_output_ndpi(s: str) -> ParseResult:
    return parse_test_output_harfbuzz(s)

def parse_test_output_mupdf(s: str) -> ParseResult:
    # no tests
    return BoolResult(Status=True)

def parse_test_output_yara(s: str) -> ParseResult:
    return parse_test_output_harfbuzz(s)

def parse_test_output_exiv2(s: str) -> ParseResult:
    pass_list, fail_list, unknown_list = [], [], []
    pattern = re.compile(r'^\d+: ([^\s]+) \(([^\)]+)\) \.\.\. (\w+)')
    for line in s.splitlines():
        m = pattern.match(line.strip())
        if m:
            _test_name, test_name, result = m.group(1).strip(), m.group(2).strip(), m.group(3).strip().upper()
            if result == "OK":
                pass_list.append(test_name)
            elif result == "FAIL" or result == "FAILED":
                fail_list.append(test_name)
            else:
                unknown_list.append(f"{test_name} ({result})")
    if pass_list or fail_list or unknown_list:
        return ListResult(PassList=pass_list, FailList=fail_list, UnknownList=unknown_list)
    return NumberResult(PassNumber=0, FailNumber=0, UnknownNumber=0)

def parse_test_output_fluent_bit(s: str) -> ParseResult:
    pass_list, fail_list, unknown_list = [], [], []
    pattern = re.compile(r'^\s*\d+/\d+\s+Test\s+#\d+:\s+([^\s]+)\s+\.+\s*(?:\*\*\*)?(Passed|Failed)')
    for line in s.splitlines():
        m = pattern.match(line.strip())
        if m:
            test_name, result = m.group(1).strip(), m.group(2).strip().upper()
            if result == "PASSED":
                pass_list.append(test_name)
            elif result == "FAILED":
                fail_list.append(test_name)
            else:
                unknown_list.append(f"{test_name} ({result})")
    if pass_list or fail_list or unknown_list:
        return ListResult(PassList=pass_list, FailList=fail_list, UnknownList=unknown_list)
    return NumberResult(PassNumber=0, FailNumber=0, UnknownNumber=0)

def parse_test_output_freeradius_server(s: str) -> ParseResult:
    if s.find("Debug : Configuration appears to be OK") != -1:
        return BoolResult(Status=True)
    else:
        return BoolResult(Status=False)

def parse_test_output_jq(s: str) -> ParseResult:
    return parse_test_output_harfbuzz(s)

def parse_test_output_libavc(s: str) -> ParseResult:
    return parse_test_output_unicorn(s)

def parse_test_output_libsass(s: str) -> ParseResult:
    # strange format, unclear meaning
    # 2349 runs, 0 assertions, 0 failures, 0 errors, 402 skips
    pattern = re.compile(r'^\s*(\d+)\s+runs?,\s*(\d+)\s+assertions?,\s*(\d+)\s+failures?,\s*(\d+)\s+errors?,\s*(\d+)\s+skips?\s*$', re.MULTILINE)
    m = pattern.search(s)
    if m:
        run_n = int(m.group(1))
        assertion_n = int(m.group(2))
        fail_n = int(m.group(3))
        error_n = int(m.group(4))
        skip_n = int(m.group(5))
        unknown_n = skip_n
        unknown_n += error_n
        pass_n = run_n - fail_n - unknown_n
        return NumberResult(PassNumber=pass_n, FailNumber=fail_n, UnknownNumber=unknown_n)
    return NumberResult(PassNumber=0, FailNumber=0, UnknownNumber=0)

def parse_test_output_Iwan(s: str) -> ParseResult:
    pass_list, fail_list, unknown_list = [], [], []
    pattern = re.compile(r'^([^\s]+) \([^\)]*\) \.\.\. (\w+)$')
    for line in s.splitlines():
        m = pattern.match(line.strip())
        if m:
            test_name, result = m.group(1).strip(), m.group(2).strip().upper()
            if result == "OK":
                pass_list.append(test_name)
            elif result == "FAIL" or result == "FAILED":
                fail_list.append(test_name)
            else:
                unknown_list.append(f"{test_name} ({result})")
    if pass_list or fail_list or unknown_list:
        return ListResult(PassList=pass_list, FailList=fail_list, UnknownList=unknown_list)
    return NumberResult(PassNumber=0, FailNumber=0, UnknownNumber=0)

def parse_test_output_md4c(s: str) -> ParseResult:
    # 652 passed, 0 failed, 0 errored, 0 skipped
    pattern = re.compile(r'^\s*(\d+)\s+passed,\s*(\d+)\s+failed,\s*(\d+)\s+errored,\s*(\d+)\s+skipped\s*$', re.MULTILINE)
    m = pattern.search(s)
    if m:
        pass_n = int(m.group(1))
        fail_n = int(m.group(2))
        error_n = int(m.group(3))
        skip_n = int(m.group(4))
        
        unknown_n = skip_n
        unknown_n += error_n
        return NumberResult(PassNumber=pass_n, FailNumber=fail_n, UnknownNumber=unknown_n)
    return NumberResult(PassNumber=0, FailNumber=0, UnknownNumber=0)

def parse_test_output_oniguruma(s: str) -> ParseResult:
    return parse_test_output_harfbuzz(s)

def parse_test_output_open62541(s: str) -> ParseResult:
    pass_list, fail_list, unknown_list = [], [], []
    pattern = re.compile(r'^\s*\d+/\d+\s+Test\s+#\d+:\s+([^\s]+)\s+\.+\s*(?:\*\*\*)?(Passed|Failed)')
    for line in s.splitlines():
        m = pattern.match(line.strip())
        if m:
            test_name, result = m.group(1).strip(), m.group(2).strip().upper()
            if result == "PASSED":
                pass_list.append(test_name)
            elif result == "FAILED":
                fail_list.append(test_name)
            else:
                unknown_list.append(f"{test_name} ({result})")
    if pass_list or fail_list or unknown_list:
        return ListResult(PassList=pass_list, FailList=fail_list, UnknownList=unknown_list)
    return NumberResult(PassNumber=0, FailNumber=0, UnknownNumber=0)


def parse_test_output_openssl(s: str) -> ParseResult:
    pass_list = []
    fail_list = []
    unknown_list = []
    pattern = re.compile(r'^(\S+)\s+\.+\s+(\w+)$')
    for line in s.splitlines():
        m = pattern.match(line.strip())
        if m:
            test_name, result = m.group(1).strip(), m.group(2).strip().upper()
            if result == "OK":
                pass_list.append(test_name)
            elif result == "FAILED":
                fail_list.append(test_name)
            else:
                unknown_list.append(f"{test_name} ({result})")
    if pass_list or fail_list or unknown_list:
        return ListResult(PassList=pass_list, FailList=fail_list, UnknownList=unknown_list)
    return NumberResult(PassNumber=0, FailNumber=0, UnknownNumber=0)

def parse_test_output_ots(s: str) -> ParseResult:
    return parse_test_output_harfbuzz(s)

def parse_test_output_rawspeed(s: str) -> ParseResult:
    pass_list = []
    fail_list = []
    unknown_list = []
    pattern = re.compile(r'^\s*\d+/\d+\s+Test\s+#\d+:\s*([^\s]+)\s+\.*\s*(Passed|Failed|Error)\b', re.IGNORECASE)
    for line in s.splitlines():
        m = pattern.match(line.strip())
        if m:
            test_name, status = m.group(1).strip(), m.group(2).strip().upper()
            if status == "PASSED":
                pass_list.append(test_name)
            elif status == "FAILED":
                fail_list.append(test_name)
            else:
                unknown_list.append(f"{test_name} ({status})")
    if pass_list or fail_list or unknown_list:
        return ListResult(PassList=pass_list, FailList=fail_list, UnknownList=unknown_list)
    return NumberResult(PassNumber=0, FailNumber=0, UnknownNumber=0)

def parse_test_output_jsoncpp(s: str) -> ParseResult:
    pass_list = []
    fail_list = []
    unknown_list = []
    pattern = re.compile(r'^Testing ([^:]+): (OK|FAILED|\s*)$')
    for line in s.splitlines():
        m = pattern.match(line.strip())
        if m:
            test_name, status = m.group(1).strip(), m.group(2).strip().upper()
            if status == "OK":
                pass_list.append(test_name)
            elif status == "FAILED":
                fail_list.append(test_name)
            else:
                unknown_list.append(f"{test_name} ({status})")
    if pass_list or fail_list or unknown_list:
        return ListResult(PassList=pass_list, FailList=fail_list, UnknownList=unknown_list)
    return NumberResult(PassNumber=0, FailNumber=0, UnknownNumber=0)

def parse_test_output_tcmalloc(s: str) -> ParseResult:
    pass_list = []
    fail_list = []
    unknown_list = []
    pattern = re.compile(r'^\/\/tcmalloc:(.+?)\s*(PASSED|FAILED|SKIP|XFAIL|XPASS|ERROR)\s*in.*$')
    for line in s.splitlines():
        m = pattern.match(line.strip())
        if m:
            print(m.groups())
            test_name, status = m.group(1).strip(), m.group(2).strip().upper()
            if status == "PASSED":
                pass_list.append(test_name)
            elif status == "FAILED":
                fail_list.append(test_name)
            else:
                unknown_list.append(f"{test_name} ({status})")
    if pass_list or fail_list or unknown_list:
        return ListResult(PassList=pass_list, FailList=fail_list, UnknownList=unknown_list)
    return NumberResult(PassNumber=0, FailNumber=0, UnknownNumber=0)

def parse_test_output_hermes(s: str) -> ParseResult:
    #   Expected Passes    : 1296
    # Unsupported Tests  : 56
    pass_n = 0
    fail_n = 0
    unknown_n = 0
    expected_passes_re = re.compile(r"^\s*Expected Passes\s*:\s*(\d+)\s*$", re.MULTILINE)
    unsupported_tests_re = re.compile(r"^\s*Unsupported Tests\s*:\s*(\d+)\s*$", re.MULTILINE)
    m_pass = expected_passes_re.search(s)
    m_unsupported = unsupported_tests_re.search(s)
    if m_pass:
        pass_n = int(m_pass.group(1))
    if m_unsupported:
        unknown_n = int(m_unsupported.group(1))
    # -- Testing: 1352 tests, 128 threads --

    total_tests_re = re.compile(r"^\s*--\s*Testing:\s*(\d+)\s*tests?,\s*(\d+)\s*threads?\s*--\s*$", re.MULTILINE)
    m_total = total_tests_re.search(s)
    if m_total:
        total_n = int(m_total.group(1))
        fail_n = total_n - pass_n - unknown_n
    if pass_n + fail_n + unknown_n > 0:
        return NumberResult(PassNumber=pass_n, FailNumber=fail_n, UnknownNumber=unknown_n)
    else:
        return NumberResult(PassNumber=0, FailNumber=0, UnknownNumber=0)

def parse_test_output_unicorn(s: str) -> ParseResult:
    pass_list = []
    fail_list = []
    unknown_list = []
    lines = s.splitlines()
    i = 0
    pattern = re.compile(r'^\[\s*(OK|FAILED)\s*\]\s*(.+)$')
    while i < len(lines):
        line = lines[i]
        if line.strip().startswith("START: Failure of the following tests is expected."):
            # skip until "END: Failure of the following tests is expected."
            i += 1
            while i < len(lines) and not lines[i].strip().startswith("END: Failure of the preceding tests was expected."):
                i += 1
            i += 1
        m = pattern.match(line.strip())
        if m:
            status, test_name = m.group(1).strip().upper(), m.group(2).strip()
            if status == "OK":
                pass_list.append(test_name)
            elif status == "FAILED":
                fail_list.append(test_name)
            else:
                unknown_list.append(f"{test_name} ({status})")
        i += 1
    if pass_list or fail_list or unknown_list:
        return ListResult(PassList=pass_list, FailList=fail_list, UnknownList=unknown_list)
    return NumberResult(PassNumber=0, FailNumber=0, UnknownNumber=0)
    



def parse_test_output_zeek(s: str) -> ParseResult:
    # [#127] plugins.init-plugin ... ok
    test_line_re = re.compile(r"^\[#(\d+)\] ([^\s]+) \.\.\. (.+)$", re.IGNORECASE)
    PassList = []
    FailList = []
    UnknownList = []
    for line in s.splitlines():
        m = test_line_re.match(line.strip())
        if m:
            test_name, result = m.group(2).strip(), m.group(3).strip().lower()
            if result == "ok":
                PassList.append(test_name)
            elif result == "failed":
                FailList.append(test_name)
            elif result in {"skipped", "skip", "not available, skipped", "error"}:
                UnknownList.append(test_name)
            else:
                UnknownList.append(f"{test_name} ({result})")
    # 10 of 1406 tests failed, 15 skipped
    result_re = re.compile(r"^\s*(\d+)\s+of\s+(\d+)\s+tests?\s+failed,\s*(\d+)\s+skipped\s*$", re.MULTILINE)
    m = result_re.search(s)
    if m:
        fail_n = int(m.group(1))
        total_n = int(m.group(2))
        skip_n = int(m.group(3))
        pass_n = total_n - fail_n - skip_n
        if fail_n != len(FailList) or skip_n != len(UnknownList):
            print(f"Warning: parsed failed-case count {len(FailList)} does not match summary {fail_n}")
            return NumberResult(PassNumber=pass_n, FailNumber=fail_n, UnknownNumber=skip_n)
        else:
            return ListResult(PassList=PassList, FailList=FailList, UnknownList=UnknownList)
    return NumberResult(PassNumber=0, FailNumber=0, UnknownNumber=0)

def parse_test_output_htslib(s: str) -> ParseResult:
    pass_list = []
    fail_list = []
    unknown_list = []
    # PASS : $tabix -f -p vcf vcf_file.tbi.tmp.vcf.gz
    pattern1 = re.compile(r"^\s*(PASS|FAIL|SKIP|XFAIL|XPASS|ERROR)\s*:\s*(.+?)\s*$")
    # bgzip round-trip no threads: .. ok
    pattern2 = re.compile(r"^\s*(.+?)\s*:\s*\.\.\s*(ok|FAILED|ERROR|skipped|skip)\s*$", re.IGNORECASE)
    # test_index:
	#     /src/htslib/test/test_view  -l 0 -b -m 14 -x /tmp/E5BT5NemT4/index.bam.csi /src/htslib/test/index.sam > /tmp/E5BT5NemT4/index.bam
    # .. ok
    for line in s.splitlines():
        m1 = pattern1.match(line.strip())
        m2 = pattern2.match(line.strip())
        if m1:
            test_name, result = m1.group(2).strip(), m1.group(1).strip().upper()
            if result == "PASS":
                pass_list.append(test_name)
            elif result == "FAIL":
                fail_list.append(test_name)
            else:
                unknown_list.append(f"{test_name} ({result})")
        elif m2:
            test_name, result = m2.group(1).strip(), m2.group(2).strip().lower()
            if result == "ok":
                pass_list.append(test_name)
            elif result == "failed":
                fail_list.append(test_name)
            else:
                unknown_list.append(f"{test_name} ({result})")
    
    # multi-line test blocks
    # test_
    block_start_re = re.compile(r"^\s*(test_[A-Za-z0-9_]+):\s*$")
    lines = s.splitlines()
    i = 0
    while i < len(lines):
        line = lines[i]
        if line.startswith("test_"):
            test_name = line.strip().rstrip(":")
            i += 1
            while i < len(lines) and (lines[i].startswith("\t") or lines[i].startswith(" ") or not lines[i].startswith("..")):
                i += 1
            if i < len(lines) and lines[i].strip().startswith(".."):
                status_line = lines[i].strip()
                m_status = re.match(r"^\.\.\s*(ok|FAILED|ERROR|skipped|skip)\s*$", status_line, re.IGNORECASE)
                if m_status:
                    result = m_status.group(1).strip().lower()
                    if result == "ok":
                        pass_list.append(test_name)
                    elif result == "failed":
                        fail_list.append(test_name)
                    else:
                        unknown_list.append(f"{test_name} ({result})")
        i += 1
    if pass_list or fail_list or unknown_list:
        return ListResult(PassList=pass_list, FailList=fail_list, UnknownList=unknown_list)
    else:
        return NumberResult(PassNumber=0, FailNumber=0, UnknownNumber=0)


def parse_test_output_igraph(s: str) -> ParseResult:
    pass_list = []
    fail_list = []
    unknown_list = []
    # Regex for individual test lines: e.g., "109/556 Test #109: test::igraph_atlas .................................   Passed    0.00 sec"
    test_line_re = re.compile(
        r"^\s*\d+/\d+\s+Test\s+#\d+:\s+([^\s]+)\s+\.*\s*(Passed|Failed|Error|\*\*\*Skipped)\b",
    )
    cutoff = 'Test project /src/igraph/build/tests'
    pos = s.find(cutoff)
    if pos != -1:
        s = s[pos + len(cutoff):]
    else:
        print("Warning: igraph test start marker not found, parsing the whole output")
    for line in s.splitlines():
        m = test_line_re.match(line.strip())
        if m:
            test_name, result = m.group(1).strip(), m.group(2).strip().lower()
            if result == "passed":
                pass_list.append(test_name)
            elif result == "failed":
                fail_list.append(test_name)
            elif result == "***skipped":
                unknown_list.append(test_name)
            else:
                unknown_list.append(f"{test_name} ({result})")
    if pass_list or fail_list or unknown_list:
        # match this 100% tests passed, 0 tests failed out of 556
        summary_re = re.compile(
            r"^\s*(\d+)\s+tests?\s+passed,\s*(\d+)\s+tests?\s+failed\s*out\s*of\s*(\d+)",
        )
        m = summary_re.search(s)
        if m:
            fail_n = int(m.group(2))
            total_n = int(m.group(3))
            if fail_n != len(fail_list):
                print(f"Warning: parsed failed-case count {len(fail_list)} does not match summary {fail_n}")
                return NumberResult(PassNumber=total_n - fail_n, FailNumber=fail_n, UnknownNumber=0)
            else:
                return ListResult(PassList=pass_list, FailList=fail_list, UnknownList=unknown_list)
        else:
            return ListResult(PassList=pass_list, FailList=fail_list, UnknownList=unknown_list)
    else:
        return NumberResult(PassNumber=0, FailNumber=0, UnknownNumber=0)

def parse_test_output_leptonica(s: str) -> ParseResult:
    return parse_test_output_harfbuzz(s)

def parse_test_output_harfbuzz(s: str) -> ParseResult:
    """
    Parse the test log:
    (1) First parse per-case PASS/FAIL/other (SKIP/XFAIL/XPASS/ERROR), return ListResult
    (2) Otherwise parse summary counts (# PASS: / # FAIL: / # SKIP: / # XFAIL: / # XPASS: / # ERROR:), return NumberResult
    (3) If there is only one test case (from per-case or summary), return BoolResult
    """
    # --- 1) Per-case match (GNU automake style: `PASS: <name>` etc.) ---
    # States treated as Unknown
    unknown_keys = {"SKIP", "XFAIL", "XPASS", "ERROR"}

    # Line starting like "PASS: name" / "FAIL: name" / "SKIP: name" ...
    line_pat = re.compile(
        r"^\s*(PASS|FAIL|SKIP|XFAIL|XPASS|ERROR)\s*:\s*(.+?)\s*$", re.MULTILINE
    )

    pass_list, fail_list, unknown_list = [], [], []

    for m in line_pat.finditer(s):
        kind, name = m.group(1).upper(), m.group(2).strip()
        # Normalize the name: strip extra spaces
        name = re.sub(r"\s+", " ", name)
        if kind == "PASS":
            pass_list.append(name)
        elif kind == "FAIL":
            fail_list.append(name)
        else:
            unknown_list.append(f"{kind}:{name}")

    # If per-case results exist, return ListResult first (1)
    if pass_list or fail_list or unknown_list:
        # (3) If there is only one case (per the per-case list)
        unique_cases = set(
            pass_list + fail_list + [x.split(":", 1)[1] for x in unknown_list]
        )
        if len(unique_cases) == 1:
            return BoolResult(
                Status=(
                    len(fail_list) == 0
                    and len(unknown_list) == 0
                    and len(pass_list) == 1
                )
            )
        return ListResult(
            PassList=pass_list, FailList=fail_list, UnknownList=unknown_list
        )

    # --- 2) Summary counts (Testsuite summary for ... # PASS: N etc.) ---
    # Allow multiple summary sections and sum them
    # Like:
    # # TOTAL: 58
    # # PASS:  54
    # # SKIP:  1
    # # FAIL:  3
    # # XPASS: 0
    # # XFAIL: 0
    # # ERROR: 0
    num_pat = re.compile(
        r"^\s*#\s*(TOTAL|PASS|FAIL|SKIP|XFAIL|XPASS|ERROR)\s*:\s*(\d+)\s*$",
        re.MULTILINE,
    )

    totals = {
        "PASS": 0,
        "FAIL": 0,
        "SKIP": 0,
        "XFAIL": 0,
        "XPASS": 0,
        "ERROR": 0,
        "TOTAL": 0,
    }
    any_summary = False
    for k, v in num_pat.findall(s):
        any_summary = True
        totals[k] += int(v)

    if any_summary:
        # (3) If the summary shows only one case
        if totals["TOTAL"] == 1:
            # If FAIL or ERROR > 0 it is False; otherwise True (a single PASS, or a single SKIP/XFAIL/XPASS could be True/False?)
            # Safer: if PASS==1 -> True; otherwise False
            status = (
                totals["PASS"] == 1 and totals["FAIL"] == 0 and totals["ERROR"] == 0
            )
            return BoolResult(Status=status)

        unknown_num = (
            totals["SKIP"] + totals["XFAIL"] + totals["XPASS"] + totals["ERROR"]
        )
        return NumberResult(
            PassNumber=totals["PASS"],
            FailNumber=totals["FAIL"],
            UnknownNumber=unknown_num,
        )

    # --- 3) Fallback for other formats: try TAP style (ok/not ok), return BoolResult only when a single case appears ---
    # TAP: "ok <n> - name" / "not ok <n> - name"
    tap_ok = re.findall(r"^\s*ok\b", s, flags=re.MULTILINE)
    tap_not_ok = re.findall(r"^\s*not\s+ok\b", s, flags=re.MULTILINE)
    if (len(tap_ok) + len(tap_not_ok)) == 1:
        return BoolResult(Status=(len(tap_not_ok) == 0))

    # If nothing can be parsed, return 0 counts
    return NumberResult(PassNumber=0, FailNumber=0, UnknownNumber=0)


def parse_test_output_wireshark(s: str) -> ParseResult:
    cut_pos = s.find("Test project")
    if cut_pos != -1:
        s = s[cut_pos:]

    # ---------- helpers ----------
    PASS_WORDS = {"ok", "passed", "xpass", "unexpected success"}
    FAIL_WORDS = {"fail", "failed", "error", "errors", "failure", "unexpected failure"}
    UNKNOWN_WORDS = {"skipped", "skip", "xfail", "expected failure"}

    def status_bucket(word: str) -> str:
        w = word.strip().lower()
        if any(w == x or w.endswith(x) for x in PASS_WORDS):
            return "pass"
        if any(w == x or w.endswith(x) for x in FAIL_WORDS):
            return "fail"
        if any(w == x or w.endswith(x) for x in UNKNOWN_WORDS):
            return "unknown"
        return ""

    # Collect per-case results (priority 1)
    pass_list: List[str] = []
    fail_list: List[str] = []
    unknown_list: List[str] = []

    # Match: single line "test_name (suite) ... STATUS"
    rx_single = re.compile(
        r"""^\s*(?:\d+:)?\s*           # optional prefix like '3:'
            (?P<name>[A-Za-z0-9_.:\-\[\]/]+)     # test name
            \s*\((?P<suite>[^)]+)\)\s*
            \.\.\.\s*
            (?P<status>[A-Za-z ]+?)               # ok / FAILED / ERROR / skipped / ...
            (?:\s+['"].*?['"])?\s*$               # optional reason
        """,
        re.X,
    )
    # Match: first line has only "test_name (suite)"; next line has description + "... STATUS"
    rx_head_only = re.compile(
        r"""^\s*(?:\d+:)?\s*
            (?P<name>[A-Za-z0-9_.:\-\[\]/]+)\s*\((?P<suite>[^)]+)\)\s*$
        """,
        re.X,
    )
    rx_follow_status = re.compile(
        r"""^\s*(?:\d+:)?\s*.*?\.\.\.\s*(?P<status>[A-Za-z ]+)(?:\s+['"].*?['"])?\s*$"""
    )

    pending_name = None  # previous case name for the two-line style

    lines = s.splitlines()
    for line in lines:
        m = rx_single.match(line)
        if m:
            name = f"{m.group('name')} ({m.group('suite')})"
            b = status_bucket(m.group("status"))
            if b == "pass":
                pass_list.append(name)
            elif b == "fail":
                fail_list.append(name)
            elif b == "unknown":
                unknown_list.append(name)
            continue

        h = rx_head_only.match(line)
        if h:
            pending_name = f"{h.group('name')} ({h.group('suite')})"
            continue

        if pending_name:
            f2 = rx_follow_status.match(line)
            if f2:
                b = status_bucket(f2.group("status"))
                if b == "pass":
                    pass_list.append(pending_name)
                elif b == "fail":
                    fail_list.append(pending_name)
                elif b == "unknown":
                    unknown_list.append(pending_name)
                pending_name = None  # clear
                continue

    # If per-case results were obtained, return first (and handle (3) the boolean when only one case)
    total_items = len(pass_list) + len(fail_list) + len(unknown_list)
    if total_items > 0:
        if total_items == 1 and len(unknown_list) == 0:
            return BoolResult(Status=(len(pass_list) == 1))
        return ListResult(
            PassList=pass_list, FailList=fail_list, UnknownList=unknown_list
        )

    # ---------- Reaching here means (1) failed; try (2) parsing counts ----------
    # Counters (summed across multiple sub-suites)
    pass_n = 0
    fail_n = 0
    unknown_n = 0

    # Plan A: parse Python unittest/pytest style "Ran N tests" + "OK(...)/FAILED(...)"
    current_ran = None
    rx_ran = re.compile(r"^\s*Ran\s+(\d+)\s+tests?\b", re.I)
    rx_ok_block = re.compile(
        r"^\s*OK(?:\s*\((.*?)\))?\s*$", re.I
    )  # e.g., OK (skipped=4)
    rx_failed_block = re.compile(
        r"^\s*FAILED\s*\((.*?)\)\s*$", re.I
    )  # e.g., FAILED (failures=1, errors=2, skipped=3)

    # Plan B: parse CTest summary
    rx_ctest_total = re.compile(
        r"""(\d+)%\s*tests\s*passed,\s*(\d+)\s*tests\s*failed\s*out\s*of\s*(\d+)""",
        re.I,
    )

    for line in lines:
        # A1: Ran N tests
        mr = rx_ran.search(line)
        if mr:
            current_ran = int(mr.group(1))
            continue
        # A2: OK (skipped=K)
        mo = rx_ok_block.search(line)
        if mo and current_ran is not None:
            skipped = 0
            if mo.group(1):
                # Parse like "skipped=4, xfail=1"
                for kv in mo.group(1).split(","):
                    k, _, v = kv.strip().partition("=")
                    if k.lower() in {"skipped", "skip"}:
                        try:
                            skipped += int(v)
                        except:
                            pass
                    elif k.lower() in {"xfail", "expected failures"}:
                        try:
                            skipped += int(v)
                        except:
                            pass
                # Other statuses counted as unknown
            unknown_n += skipped
            pass_n += max(0, current_ran - skipped)  # OK block has no failures
            current_ran = None
            continue
        # A3: FAILED (failures=..., errors=..., skipped=...)
        mf = rx_failed_block.search(line)
        if mf and current_ran is not None:
            kvs = {}
            for kv in mf.group(1).split(","):
                k, _, v = kv.strip().partition("=")
                k = k.lower().strip()
                try:
                    kvs[k] = int(v)
                except:
                    pass
            fails = kvs.get("failures", 0) + kvs.get("errors", 0)
            skipped = kvs.get("skipped", 0)
            # Other unknown keys (e.g. xfail) counted as unknown
            extra_unknown = sum(
                v for k, v in kvs.items() if k not in {"failures", "errors", "skipped"}
            )
            fail_n += fails
            unknown_n += skipped + extra_unknown
            passed_here = current_ran - fails - skipped - extra_unknown
            pass_n += max(0, passed_here)
            current_ran = None
            continue

        # B: CTest summary
        mc = rx_ctest_total.search(line)
        if mc:
            failed = int(mc.group(2))
            total = int(mc.group(3))
            fail_n += failed
            pass_n += max(0, total - failed)
            # CTest summary does not include skipped, count as 0
            # Do not return; allow merging/summing with A
            continue

    # If count information was obtained
    if pass_n + fail_n + unknown_n > 0:
        if (pass_n + fail_n + unknown_n) == 1 and unknown_n == 0:
            return BoolResult(Status=(pass_n == 1))
        return NumberResult(
            PassNumber=pass_n, FailNumber=fail_n, UnknownNumber=unknown_n
        )

    # ---------- Still no result: try to grab directly if there is only one "obvious status" ----------
    # Simple fallback: if the text contains exactly one explicit PASS/FAIL
    text_low = s.lower()
    has_pass = any(w in text_low for w in PASS_WORDS)
    has_fail = any(w in text_low for w in FAIL_WORDS)
    has_unknown = any(w in text_low for w in UNKNOWN_WORDS)
    if has_pass ^ has_fail and not has_unknown:
        return BoolResult(Status=has_pass)

    # Final fallback: cannot determine, return 0 counts
    return NumberResult(PassNumber=0, FailNumber=0, UnknownNumber=0)

def parse_test_output_wireshark2(s: str) -> ParseResult:
    """
    Specialized parser for Wireshark pytest-style output.

    Extracts per-item failures/errors and skipped, and falls back to
    summary counts like:
      "5 failed, 837 passed, 35 skipped, 5 errors in 20.64s"
    """
    # Prefer focusing on the final short summary section for accurate itemization
    text = s
    marker = "short test summary info"
    idx = text.lower().rfind(marker)
    if idx != -1:
        text = text[idx:]

    pass_list: List[str] = []
    fail_list: List[str] = []
    unknown_list: List[str] = []

    # Regexes (case-insensitive) for pytest short summary lines
    rx_pass = re.compile(r"^\s*PASSED\s+(.+)$", re.IGNORECASE | re.MULTILINE)
    rx_fail_or_err = re.compile(r"^\s*(FAILED|ERROR)\s+(.+?)(?:\s+-\s+.*)?\s*$", re.IGNORECASE | re.MULTILINE)
    rx_skip = re.compile(r"^\s*SKIPPED\s*(?:\[\d+\])?\s+(.+?)\s*$", re.IGNORECASE | re.MULTILINE)
    rx_xfail = re.compile(r"^\s*XFAIL(?:ED)?\s+(.+)$", re.IGNORECASE | re.MULTILINE)
    rx_xpass = re.compile(r"^\s*XPASS(?:ED)?\s+(.+)$", re.IGNORECASE | re.MULTILINE)

    # Collect items
    for m in rx_pass.finditer(text):
        nodeid = m.group(1).strip()
        if nodeid and nodeid not in pass_list:
            pass_list.append(nodeid)
    for m in rx_fail_or_err.finditer(text):
        nodeid = m.group(2).strip()
        if nodeid and nodeid not in fail_list:
            fail_list.append(nodeid)
    for m in rx_skip.finditer(text):
        info = m.group(1).strip()
        if info and info not in unknown_list:
            unknown_list.append(info)
    for m in rx_xfail.finditer(text):
        info = m.group(1).strip()
        if info and info not in unknown_list:
            unknown_list.append(info)
    for m in rx_xpass.finditer(text):
        nodeid = m.group(1).strip()
        if nodeid and nodeid not in pass_list:
            pass_list.append(nodeid)

    # If we have any itemized results, return list result (single-item -> Bool)
    if pass_list or fail_list or unknown_list:
        total_items = len(pass_list) + len(fail_list) + len(unknown_list)
        if total_items == 1 and len(unknown_list) == 0:
            return BoolResult(Status=(len(pass_list) == 1))
        return ListResult(PassList=pass_list, FailList=fail_list, UnknownList=unknown_list)

    # Fallback to summary counts like: "5 failed, 837 passed, 35 skipped, 5 errors in 20.64s"
    counts = {k: 0 for k in ("passed", "failed", "skipped", "errors", "xfailed", "xpassed")}
    for key in counts.keys():
        mkey = re.search(rf"(?mi)\b(\d+)\s+{key}\b", s)
        if mkey:
            counts[key] = int(mkey.group(1))

    total = sum(counts.values())
    if total > 0:
        pass_n = counts["passed"] + counts["xpassed"]
        fail_n = counts["failed"] + counts["errors"]
        unknown_n = counts["skipped"] + counts["xfailed"]
        if (pass_n + fail_n + unknown_n) == 1 and unknown_n == 0:
            return BoolResult(Status=(pass_n == 1))
        return NumberResult(PassNumber=pass_n, FailNumber=fail_n, UnknownNumber=unknown_n)

    # Last resort
    return NumberResult(PassNumber=0, FailNumber=0, UnknownNumber=0)

def parse_test_output_wolfssl(s: str) -> ParseResult:
    """
    Parse wolfSSL test output, extracting test name and result for each test.
    Returns a ListResult with PassList, FailList, and UnknownList.
    """
    test_line_re = re.compile(r"^([A-Za-z0-9\-]+)\s+test ([a-zA-Z0-9_\-!]+)!$")
    PassList = []
    FailList = []
    UnknownList = []
    for line in s.splitlines():
        m = test_line_re.match(line.strip())
        if m:
            test_name, result = m.group(1), m.group(2).lower()
            if result == "passed":
                PassList.append(test_name)
            elif result == "failed":
                FailList.append(test_name)
            else:
                UnknownList.append(f"{test_name} ({result})")
    if PassList or FailList or UnknownList:
        return ListResult(PassList=PassList, FailList=FailList, UnknownList=UnknownList)
    else:
        return NumberResult(PassNumber=0, FailNumber=0, UnknownNumber=0)

def parse_test_output_util_linux(s: str) -> ParseResult:
    test_summary_re = re.compile(r"\s*(\d+)\s+tests\s+of\s+(\d+)\s+FAILED")
    m = test_summary_re.search(s)
    if m:
        fail_count = int(m.group(1))
        total_count = int(m.group(2))
        pass_count = total_count - fail_count
        return NumberResult(PassNumber=pass_count, FailNumber=fail_count, UnknownNumber=0)
    else:
        return NumberResult(PassNumber=0, FailNumber=0, UnknownNumber=0)

def parse_test_output_selinux(s: str) -> ParseResult:
    test_line_re = re.compile(r"^Test:(.+)\.\.\.(FAILED|passed)$")
    PassList = []
    FailList = []
    UnknownList = []
    for line in s.splitlines():
        m = test_line_re.match(line.strip())
        if m:
            test_name, result = m.group(1).strip(), m.group(2).lower()
            if result == "passed":
                PassList.append(test_name)
            elif result == "failed":
                FailList.append(test_name)
            else:
                UnknownList.append(f"{test_name} ({result})")
    if PassList or FailList or UnknownList:
        return ListResult(PassList=PassList, FailList=FailList, UnknownList=UnknownList)
    else:
        summary_re = re.compile(
    r"^\s*tests\s+(\d+)\s+(\d+)\s+(\d+)\s+(\d+)\s+(\d+)\s*$"
            )
        passed_n = 0
        failed_n = 0
        unknown_n = 0
        for line in s.splitlines():
            m = summary_re.match(line)
            if m:
                total, ran, passed, failed, inactive = map(int, m.groups())
                unknown = inactive  # Treat inactive as unknown
                passed_n += passed
                failed_n += failed
                unknown_n += unknown
        return NumberResult(PassNumber=passed_n, FailNumber=failed_n, UnknownNumber=unknown_n)

def parse_test_output_php_src(s: str) -> ParseResult:
    # [1;32mPASS[0m
    test_re = re.compile(r"\x1b\[\d+;\d+m(PASS|FAIL|SKIP|XFAIL|XPASS|ERROR)\x1b\[0m.*\[(.*?)\]")
    fail_list = []
    pass_list = []
    unknown_list = []
    for line in s.splitlines():
        m = test_re.search(line)
        if m:
            status, test_name = m.group(1), m.group(2)
            if status == "PASS":
                pass_list.append(test_name)
            elif status == "FAIL":
                fail_list.append(test_name)
            else:
                unknown_list.append(f"{test_name} ({status})")
    if pass_list or fail_list or unknown_list:
        return ListResult(PassList=pass_list, FailList=fail_list, UnknownList=unknown_list)
    else:
        return NumberResult(PassNumber=0, FailNumber=0, UnknownNumber=0)

def parse_test_output_lua(s: str) -> ParseResult:
    # Split into sections based on ***** FILE '...' *****
    sections = re.split(r'^\s*\*+\s*FILE\s+\'([^\']+)\'\s*\*+\s*$', s, flags=re.MULTILINE)
    pass_list = []
    fail_list = []
    unknown_list = []
    
    # Process each section (sections[0] is before first match, then pairs of filename + content)
    for i in range(1, len(sections), 2):
        filename = sections[i]
        content = sections[i + 1] if i + 1 < len(sections) else ""
        
        # Check for "OK" in the section (indicates pass)
        if "OK" in content:
            pass_list.append(filename)
        # Check for failure indicators (e.g., "FAILED", or missing "OK")
        elif re.search(r'\b(FAILED|FAIL)\b', content, re.IGNORECASE):
            fail_list.append(filename)
        else:
            unknown_list.append(filename)
    
    # If we have per-section results, return ListResult
    if pass_list or fail_list or unknown_list:
        total_sections = len(pass_list) + len(fail_list) + len(unknown_list)
        if total_sections == 1:
            # Single section: return BoolResult based on pass/fail
            status = len(pass_list) == 1 and len(fail_list) == 0
            return BoolResult(Status=status)
        return ListResult(PassList=pass_list, FailList=fail_list, UnknownList=unknown_list)
    
    # Fallback: Count "OK" lines for a summary (no detailed failures assumed)
    ok_count = len(re.findall(r'\bOK\b', s))
    total_sections = len(re.findall(r'^\s*\*+\s*FILE\s+', s, re.MULTILINE))
    fail_count = 0  # No explicit fails in this log, but could be extended
    unknown_count = total_sections - ok_count - fail_count
    
    if total_sections > 0:
        if total_sections == 1:
            return BoolResult(Status=ok_count == 1)
        return NumberResult(PassNumber=ok_count, FailNumber=fail_count, UnknownNumber=unknown_count)
    
    # Ultimate fallback: Check for "final OK !!!" (overall pass)
    if "final OK !!!" in s:
        return BoolResult(Status=True)
    else:
        return BoolResult(Status=False)
    
def parse_test_output_libsrtp(s: str) -> ParseResult:
    cutoff = 'running libsrtp2 test applications...'
    pos = s.find(cutoff)
    if pos != -1:
        s = s[pos + len(cutoff):]
    else:
        print("Warning: libsrtp2 test start marker not found, parsing the whole output")
    
    pass_list = []
    fail_list = []
    unknown_list = []

    patterns = [
        (r'running (.*)\.\.\.passed', 'passed'),  # Pattern 1
        (r'Test (.*)\.\.\. \[   OK   \]', 'OK'),  # Pattern 2
        (r'testing (.*)\(\)\.\.\.passed', 'passed'),  # Pattern 3
        (r'(.*) : done \(test passed\)', 'passed'),  # Pattern 4
        (r'(.*) : done \(test passed\)', 'passed'),  # For scripts
    ]

    possible_fail_patterns = [
        r'running (.*)\.\.\.failed',
        r'Test (.*)\.\.\. \[ FAILED \]',
        r'testing (.*)\.\.\.failed',
        r'(.*) : done \(test failed\)',
    ]

    # Parse successes
    for pattern, status in patterns:
        matches = re.findall(pattern, s, re.MULTILINE)
        for match in matches:
            test_name = match.strip()
            if status in ['passed', 'OK', 'done']:
                pass_list.append(test_name)
    
    # Parse failures
    for pattern in possible_fail_patterns:
        matches = re.findall(pattern, s, re.MULTILINE)
        for match in matches:
            test_name = match.strip()
            fail_list.append(test_name)

    # Parse block-level tests
    lines = s.split('\n')
    i = 0
    while i < len(lines):
        line = lines[i].strip()
        if line.startswith('testing ') and not line.endswith('...passed') and not line.endswith('...failed'):
            # Start of a block: extract test name
            test_name = line[len('testing '):].strip()
            i += 1
            # Skip # lines and tabbed sub-tests
            while i < len(lines) and (lines[i].strip().startswith('#') or lines[i].startswith('\t')):
                i += 1
            # Check the next non-skipped line for status
            if i < len(lines):
                status_line = lines[i].strip()
                if status_line == 'passed':
                    pass_list.append(test_name)
                elif status_line == 'failed':
                    fail_list.append(test_name)
                i += 1  # Move past the status line
            else:
                i += 1
        else:
            i += 1

    # If any tests found, return ListResult
    if pass_list or fail_list:
        return ListResult(PassList=pass_list, FailList=fail_list, UnknownList=[])
    
    # Fallback: Check for overall success indicators
    success_patterns = [
        r'libsrtp2 test applications passed\.',
        r'crypto test applications passed\.',
    ]
    success_count = sum(1 for pattern in success_patterns if re.search(pattern, s))
    
    return NumberResult(PassNumber=success_count, FailNumber=len(success_patterns) - success_count, UnknownNumber=0)
    
    

def parse_test_output_cblosc2(s: str) -> ParseResult:
    """
    Parse CTest-style output, e.g.
      1/1642 Test  #1: test_api ..........................   Passed    0.01 sec
    Fallback to the summary line:
      100% tests passed, 0 tests failed out of 1642
    """
    text = s
    m_cut = re.search(r"(?mi)^Test\s+project\b", text)
    if m_cut:
        text = text[m_cut.start():]

    pass_list, fail_list, other_list = [], [], []
    seen = set()

    def add(name: str, norm: str):
        if name in seen:
            if norm == "fail":
                if name in pass_list: pass_list.remove(name)
                if name in other_list: other_list.remove(name)
                if name not in fail_list: fail_list.append(name)
            elif norm == "other":
                if name not in fail_list and name not in other_list:
                    if name in pass_list: pass_list.remove(name)
                    other_list.append(name)
        else:
            if norm == "fail":
                fail_list.append(name)
            elif norm == "other":
                other_list.append(name)
            else:
                pass_list.append(name)
            seen.add(name)

    ctest_line_re = re.compile(
        r"""(?mx)
        ^(?:\s*\d+/\d+\s+)?            # optional "1326/1638 "
        Test\s*#\s*\d+\s*:\s*          # "Test #1334:"
        (?P<name>.*?)                      # name
        \s+\.{3,}\s+                     # dot leader
        (?P<status>(?:\*{3}\w+|\w+))     # status
        (?:\s+|$)
        """
    )

    def _norm_ctest_status(raw: str) -> str:
        t = raw.strip().lower().strip("*")
        if any(k in t for k in ("failed", "failure", "timeout", "timedout", "segfault", "error")):
            return "fail"
        if any(k in t for k in ("passed", "success", "ok")):
            return "pass"
        if any(k in t for k in ("skipped", "disabled", "notrun", "not run", "ignored")):
            return "other"
        return "other"

    for m in ctest_line_re.finditer(text):
        add(m.group("name").strip(), _norm_ctest_status(m.group("status")))

    failed_block = re.search(r"(?s)The\s+following\s+tests\s+FAILED:.*?(?:\n\s*\n|\Z)", text)
    if failed_block:
        for fm in re.finditer(r"^\s*\d+\s*-\s*(?P<name>.+?)\s*\(\s*Failed\s*\)\s*$", failed_block.group(0), re.MULTILINE):
            name = fm.group("name").strip()
            if name not in fail_list:
                if name in pass_list: pass_list.remove(name)
                if name in other_list: other_list.remove(name)
                fail_list.append(name); seen.add(name)

    notrun_block = re.search(r"(?s)The\s+following\s+tests\s+did\s+not\s+run:.*?(?:\n\s*\n|\Z)", text)
    if notrun_block:
        for nm in re.finditer(r"^\s*\d+\s*-\s*(?P<name>.+?)(?:\s*\(\s*[^)]+\s*\))?\s*$", notrun_block.group(0), re.MULTILINE):
            name = nm.group("name").strip()
            if name not in fail_list and name not in pass_list and name not in other_list:
                other_list.append(name); seen.add(name)

    if len(seen) == 1:
        only = (pass_list or fail_list or other_list)[0]
        return BoolResult(Status=(only in pass_list))
    if len(seen) > 0:
        return ListResult(
            PassList=sorted(set(pass_list)),
            FailList=sorted(set(fail_list)),
            UnknownList=sorted(set(other_list)),
        )

    msum = re.search(r"(?mi)^\s*\d+%?\s*tests\s*passed,\s*(?P<failed>\d+)\s*tests\s*failed\s*out\s*of\s*(?P<total>\d+)\s*$", text)
    if msum:
        failed = int(msum.group("failed")); total = int(msum.group("total"))
        passed = max(total - failed, 0)
        return NumberResult(PassNumber=passed, FailNumber=failed, UnknownNumber=0)

    return NumberResult(PassNumber=0, FailNumber=0, UnknownNumber=0)


# ======================================================================
# Serialize a ParseResult's text representation back into a JSON dict.
# (Merged from the former parse_results_to_json.py.)
# Supports three formats: ListResult, NumberResult, BoolResult
# ======================================================================

def parse_list_result(text: str) -> Dict[str, Any]:
    """Parse ListResult format"""
    # Find the positions of the three sections
    pass_match = re.search(
        r"=+\nPass (\d+)\n=+\n(.*?)(?=\n=+\nFail|\Z)", text, re.DOTALL
    )
    fail_match = re.search(
        r"=+\nFail (\d+)\n=+\n(.*?)(?=\n=+\nUnknown|\Z)", text, re.DOTALL
    )
    unknown_match = re.search(
        r"=+\nUnknown (\d+)\n=+\n(.*?)(?=\n=+|\Z)", text, re.DOTALL
    )

    result = {"PassList": [], "FailList": [], "UnknownList": []}

    if pass_match:
        items = pass_match.group(2).strip()
        if items:
            result["PassList"] = [
                line.strip() for line in items.split("\n") if line.strip()
            ]

    if fail_match:
        items = fail_match.group(2).strip()
        if items:
            result["FailList"] = [
                line.strip() for line in items.split("\n") if line.strip()
            ]

    if unknown_match:
        items = unknown_match.group(2).strip()
        if items:
            result["UnknownList"] = [
                line.strip() for line in items.split("\n") if line.strip()
            ]

    return result


def parse_number_result(text: str) -> Dict[str, Any]:
    """Parse NumberResult format"""
    pass_match = re.search(r"Pass:\s*(\d+)", text)
    fail_match = re.search(r"Fail:\s*(\d+)", text)
    unknown_match = re.search(r"Unknown:\s*(\d+)", text)
    total_match = re.search(r"Total:\s*(\d+)", text)

    return {
        "PassNumber": int(pass_match.group(1)) if pass_match else 0,
        "FailNumber": int(fail_match.group(1)) if fail_match else 0,
        "UnknownNumber": int(unknown_match.group(1)) if unknown_match else 0,
    }


def parse_bool_result(text: str) -> Dict[str, Any]:
    """Parse BoolResult format"""
    status_match = re.search(r"Status:\s*(PASS|FAIL)", text, re.IGNORECASE)

    return {
        "Status": status_match.group(1).upper() == "PASS" if status_match else False
    }


def extract_meta(text: str) -> Dict[str, Any]:
    """Extract the metadata from the file header"""
    meta = {}

    script_match = re.search(r"Script:\s*(\d+)", text)
    if script_match:
        meta["script"] = int(script_match.group(1))

    rc_match = re.search(r"Return Code:\s*(-?\d+)", text)
    if rc_match:
        meta["return_code"] = int(rc_match.group(1))

    time_match = re.search(r"Parsing Time:\s*(.+)", text)
    if time_match:
        meta["parsing_time"] = time_match.group(1).strip()

    return meta


def parse_single_file(file_path: Path) -> Dict[str, Any]:
    """Parse a single file"""
    try:
        text = file_path.read_text(encoding="utf-8", errors="replace")

        # Extract localid
        script_match = re.search(r"Script:\s*(\d+)", text)
        localid = int(script_match.group(1)) if script_match else None

        # Select parser and type based on content type
        if "ListResult" in text:
            result_type = "ListResult"
            content = parse_list_result(text)
        elif "NumberResult" in text:
            result_type = "NumberResult"
            content = parse_number_result(text)
        elif "BoolResult" in text:
            result_type = "BoolResult"
            content = parse_bool_result(text)
        else:
            result_type = "Unknown"
            content = {}

        # Build the final result
        result = {"localid": localid, "type": result_type}
        result.update(content)

        return result

    except Exception as e:
        return {"localid": None, "type": "Error", "error": str(e)}


if __name__ == "__main__":
    import sys

    if len(sys.argv) > 2:
        command = sys.argv[1]
        localid = int(sys.argv[2])

        if command == "get":
            ### Update commit ###
            _path = "./new_commit_check.csv"
            test_base_commit = ""
            with open(_path, "r") as f:
                lines = f.readlines()
            for line in lines:
                if str(localid) in line:
                    test_base_commit = line.strip().split(",")[2]
                    break
            assert test_base_commit != "", f"Could not find commit for {localid}"
            bash = open("temp_test_script.sh", "r").read()
            
            # Find the git checkout line; if present, change it to the correct commit
            git_checkout_line = ""
            git_checkout_line_index = -1
            bash_lines = bash.splitlines()
            for i, line in enumerate(bash_lines):
                if "git checkout" in line:
                    if "&&" in line:
                        raise Exception(f"git checkout line contains &&!!!")
                    git_checkout_line = line
                    git_checkout_line_index = i
                    break
            if git_checkout_line:
                # Change the git checkout line to the correct commit
                bash_lines[git_checkout_line_index] = "git checkout " + test_base_commit
                bash = "\n".join(bash_lines)
                print(f"Changed git checkout line to the correct commit: {git_checkout_line} -> {test_base_commit}")
            else:
                # If there is no git checkout line, raise an error
                raise Exception(f"git checkout line not found")
            
            with open("temp_test_script.sh", "w") as f:
                f.write(bash)
            ### END ###
            
            print(f"\n===== Attempting to get output for {localid} =====\n")
            get_test_output(localid=localid)
        elif command == "parse":
            print(f"\n===== Attempting to parse report =====\n")
            temp_test_output = open("temp_test_output.log", "r").read()

            ### Verify commit ###
            _path = "./new_commit_check.csv"
            test_base_commit = ""
            with open(_path, "r") as f:
                lines = f.readlines()
            for line in lines:
                if str(localid) in line:
                    test_base_commit = line.strip().split(",")[2]
                    break
            if test_base_commit not in temp_test_output:
                raise Exception(
                    f"Wrong: commit mismatch (the base commit was not found in the test output)"
                )
            ### END ###

            parse_result = parse_test_output(localid, temp_test_output)
            with open("temp_test_parse.txt", "w") as f:
                f.write(str(parse_result))
            print(f"\n===== Parsing complete =====\n")
        else:
            print("Usage: python parse_test_report.py <get|parse> <localid>")
            sys.exit(1)
    else:
        print("Usage: python parse_test_report.py <get|parse> <localid>")
        sys.exit(1)
