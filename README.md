# toolkit-data

This repository contains static demo data for the [Toolkit](https://github.com/cognitedata/toolkit) project.

It is organized as follows:

```bash
📦toolkit-data
 ┣ 📂data - Root folder for data.
 ┃ ┣ 📂publicdata - The dataset names 'publicdata'
 ┃ . 📂<another dataset> 
 ┃ ┗ 📂<another dataset>
 ┣ 📜.gitignore - Ignore files that should not be checked into Git.
 ┗ 📜README.md - This file
```

The datasets in this repository should be treated as read-only (immutable). If you need to modify the data, make a copy of the dataset, give it a new descriptive name, and modify the copy.

## Use the CDN

Using data directly from GitHub will be rate limited. Instead, use the CDN link pattern below to access the data:

**location in repository:**

```html  
./data/<directory>/<filename>

for example

./data/publicdata/assets.Table.csv

```

**storage bucket location:**

```html

gs://apps-cdn-bucket-cognitedata-production/toolkit/<directory>/<filename>

for example

gs://apps-cdn-bucket-cognitedata-production/toolkit/publicdata/assets.Table.csv

```

**Download location:**

```html  
https://apps-cdn.cogniteapp.com/toolkit/<directory>/<filename>
<<<<<<< HEAD

for example

https://apps-cdn.cogniteapp.com/toolkit/publicdata/assets.Table.csv

=======
>>>>>>> bf34751d1226f2f6adba49ac84541f0090a53774
```

## Upload to CDN

Data in `./data` is automatically uploaded when it is merged to `main` using the GitHub Actions workflow in `.github/workflows/upload-to-cdn.yaml`.
This repository contains data for the [Cognite Toolkit](https://docs.cognite.com/cdf/deploy/cdf_toolkit/)
