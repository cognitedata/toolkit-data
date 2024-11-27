# toolkit-data

This repository contains static demo data for the [Toolkit](https://github.com/cognitedata/toolkit) project.

## Use the CDN

Using data directly from GitHub will be rate limited. Instead, use the CDN link pattern below to access the data:

**location in repository:**

```html  
./data/<directory>/<filename>
```

**CDN location:**

```html  
https://apps-cdn.cogniteapp.com/toolkit-data/<directory>/<filename>
```

## Upload to CDN

Data in `./data` is automatically uploaded when it is merged to `main` using the GitHub Actions workflow in `.github/workflows/upload-to-cdn.yaml`.
