当前代码基本可以实现普通依赖的下载，但是还是存在优化空间，如下所示

获取 python 3.9 的 pytest 库的本地依赖，执行如下命令

```markdown
auto-wheel -p 3.9 -pkg pytest
```

随后将生成的依赖打包放到 python 3.9 的虚拟环境下，执行 pip install --no-index --find-links=. -r requirements-offline.txt 进行安装，结果如下所示

```markdown
PS C:\Users\xytcs\Desktop\39> .\.venv\Scripts\activate
(.venv) PS C:\Users\xytcs\Desktop\39> pip install --no-index --find-links=. -r requirements-offline.txt
Looking in links: .
Processing c:\users\xytcs\desktop\39\colorama-0.4.6-py2.py3-none-any.whl (from -r requirements-offline.txt (line 6))
Processing c:\users\xytcs\desktop\39\iniconfig-2.1.0-py3-none-any.whl (from -r requirements-offline.txt (line 7))
Processing c:\users\xytcs\desktop\39\packaging-25.0-py3-none-any.whl (from -r requirements-offline.txt (line 8))
Processing c:\users\xytcs\desktop\39\pluggy-1.6.0-py3-none-any.whl (from -r requirements-offline.txt (line 9))
Processing c:\users\xytcs\desktop\39\pygments-2.19.2-py3-none-any.whl (from -r requirements-offline.txt (line 10))
Processing c:\users\xytcs\desktop\39\pytest-8.4.2-py3-none-any.whl (from -r requirements-offline.txt (line 11))
INFO: pip is looking at multiple versions of pytest to determine which version is compatible with other requirements. This could take a while.
ERROR: Could not find a version that satisfies the requirement exceptiongroup>=1; python_version < "3.11" (from pytest) (from versions: none)
ERROR: No matching distribution found for exceptiongroup>=1; python_version < "3.11"
```





请根据上述情况，结合当前项目提出合适的优化方案