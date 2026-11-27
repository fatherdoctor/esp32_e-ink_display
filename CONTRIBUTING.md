# Contributing

Every change starts from an issue. That way anyone can see what is planned and why before a pull request shows up.

1. **Open an issue first.** Say what you want to change and why. If an issue for it already exists, use that one.
2. **Work on a branch** and open a pull request into `main`. Put one change in each pull request. Never push to
   `main`.
3. **Link the issue.** The pull request description says `Closes #n`, so the issue closes when the pull request
   merges.
4. **Keep later work open.** If a change is wanted but not now, its issue stays open with the `backlog` label.
   Don't close it just because nobody is working on it.

Run the checks CI runs before you push: `python -m pip install -r requirements-test.txt`, then `python -m unittest discover -s tests -v` and `python tools/check_public_tree.py`. The README has the build and setup steps.
