@rem fk: the agent's one command (bin\fk.py beside this file; the run folder is the one above bin\)
@set "FK_RUN=%~dp0.."
@if exist "C:\fk-player\python\python.exe" ("C:\fk-player\python\python.exe" "%~dp0fk.py" %*) else (python "%~dp0fk.py" %*)
