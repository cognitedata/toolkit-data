# toolkit-data

This repository contains data for the [Cognite Toolkit](https://docs.cognite.com/cdf/deploy/cdf_toolkit/)

The repository is organized as follows:

```bash
📦toolki-data
 ┣ 📂data - Root folder for data.
 ┃ ┣ 📂publicdata - The dataset names 'publicdata'
 ┃ . 📂<another dataset> 
 ┃ ┗ 📂<another dataset>
 ┣ 📜.gitignore - Ignore files that should not be checked into Git.
 ┗ 📜README.md - This file
```

The datasets in this repository should be treated as read-only (immutable). If you need to modify the data, 
make a copy of the dataset, give it a new descriptive name, and modify the copy.
