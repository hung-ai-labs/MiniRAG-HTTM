# 2WikiMultiHopQA dataset

The original `data_ids_april7.zip` archive is split into 45 MiB parts so it can
be stored on GitHub without Git LFS. Reassemble it from this directory before
extracting the dataset.

On Linux or macOS:

```sh
cat data_ids_april7.zip.part-* > data_ids_april7.zip
```

On Windows (`cmd.exe`):

```bat
copy /b data_ids_april7.zip.part-00+data_ids_april7.zip.part-01+data_ids_april7.zip.part-02+data_ids_april7.zip.part-03+data_ids_april7.zip.part-04+data_ids_april7.zip.part-05 data_ids_april7.zip
```

Expected SHA-256:

```text
95DF2BF56FDABE034E27AEBC580E02264232203CF52552F9EFE8A919E5529EEF
```

The archive contains `train.json`, `dev.json`, `test.json`, and
`id_aliases.json`.
