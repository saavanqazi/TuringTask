# Connector task 1: round 10. Package hardening 6 like the accepted reference (Windows CMD)

Start every CMD window with:

```bat
call "%USERPROFILE%\.config\harbor\harbor-env.cmd"
set "TASK=C:\turing\conn\the-meetings-still-waiting-on-a-yes"
```

Save these three files into `C:\turing\scratch\`:
- `c1_pack.zip`
- `consistency_llm.py`
- `make_c1_package.py`

**Do not change any task file before step 1 is done.** The stability runs must be on the same task checksum as the battery (`b35c3f8d…`).

## 1. Stability: three more oracle runs, task unchanged

```bat
harbor run -p "%TASK%" -a oracle --ve OPENAI_API_KEY=%OPENAI_API_KEY% --ve OPENAI_BASE_URL=%OPENAI_BASE_URL% --ve JUDGE_MODEL=%JUDGE_MODEL% -o C:\harbor-jobs --job-name oracle-c1-h6-stab -n 1 -k 3 -y
for /d %d in (C:\harbor-jobs\oracle-c1-h6-stab\*) do @if exist "%d\verifier\reward.txt" (echo %~nxd & type "%d\verifier\reward.txt")
```

You need three `1.0`. It takes about 30 minutes. Leave `C:\harbor-jobs\glm-c1-h6` and `C:\harbor-jobs\oracle-c1-h6` where they are: step 5 reads them, including their `trial.log` files.

## 2. Add README, review.csv and consistency/, and remove the stale harbor check

```bat
cd /d C:\turing\conn
tar -xf C:\turing\scratch\c1_pack.zip
git rm -r -q "%TASK%\evaluations\harbor_check"
git status --short
```

`git status` must show:
- `README.md` and `review.csv` as new;
- `consistency/mutations.json`, `requirements.json` and `shortcut_audit.md` as modified;
- `evaluations/harbor_check` files as deleted. They describe the original mined task; the platform's own check replaces them later.

## 3. The LLM-backed consistency files (readers, envelope, rubric validation)

```bat
C:\turing\venv312\Scripts\pip install -q pydantic jsonpath-ng tenacity
C:\turing\venv312\Scripts\python C:\turing\scratch\consistency_llm.py "%TASK%" "C:\harbor-jobs\glm-c1-h6\the-meetings-still-waiting-on-a__BaFoQu9"
```

It calls your judge endpoint about 25 times, which takes a few minutes. The last three lines should read:
- `readers: {... '4/4', ... '4/4', ... '4/4'}`. 3/4 on one line is acceptable; I will read the verbatim notes.
- `envelope: ['V1 terse: 47/47', 'V2 verbose: 47/47', 'V3 report-style: 47/47']`
- `rubric cases as expected: 6 / 6`

If any renderings score below 47/47, or fewer than 6 rubric cases come out as expected, send me `%TASK%\consistency\envelope.json` and `mutations.json` before going on.

Then commit:

```bat
git add -A
git commit -m "Package: README, review.csv, consistency/ for hardening 6; stale harbor_check removed"
```

## 4. Check that the task files are still the battery's

```bat
fc /b "%TASK%\instruction.md" "%TASK%\environment\_app\instruction.md"
fc /b "%TASK%\task.toml" "%TASK%\environment\_app\task.toml"
fc /b "%TASK%\tests\manifest.json" "%TASK%\environment\_app\tests\manifest.json"
```

All three must say `no differences encountered`.

## 5. Assemble and zip the package

```bat
C:\turing\venv312\Scripts\python C:\turing\scratch\make_c1_package.py "%TASK%" C:\harbor-jobs C:\turing\scratch\c1_submit
```

It must end with:

```
PACKAGED C:\turing\scratch\c1_submit\the-meetings-still-waiting-on-a-yes.zip (… files)
  oracle 1.0 | stability ['1.0', '1.0', '1.0'] | glm-5.2 ['0.0293', '0.0293', '1.0', '1.0'] | checksum b35c3f8d
```

If it prints `NOT PACKAGED:` with a list, send me the list; it never zips a package with a problem in it. The script also:
- refuses to package anything that looks like an API key;
- replaces the judge endpoint address with `${OPENAI_BASE_URL}` in the copied run records.

## 6. Upload, gate, final zip

1. Upload `C:\turing\scratch\c1_submit\the-meetings-still-waiting-on-a-yes.zip`, then run the Delivery Gate / Harbor Check.
2. When it finishes:
   - put its `qc_report.html` into `%TASK%\`;
   - put its harbor check output (the files the platform gives you for it) into `%TASK%\evaluations\harbor_check\`.
3. Re-run step 5. The script carries both into the new zip.
4. Upload that zip as the new version and submit.

## SEND

1. The three stability rewards from step 1.
2. The last three lines of step 3.
3. The two `PACKAGED` lines from step 5.
4. The platform's findings, if the gate raises any.
