# Final package assembly — 2026-09-27

Run the two download commands from **Mac Terminal** first.  Replace the IP only if the
EC2 console shows a new public address.

```bash
KEY="/Users/pocketfm/Downloads/ber-runner.pem"
EC2="ubuntu@52.91.37.155"
ROOT="/Users/pocketfm/Desktop/amazon_ML/Working Folder"

scp -o IdentitiesOnly=yes -i "$KEY" \
  "$EC2:~/ber/output/matching_results.tsv" \
  "$ROOT/submit_folder/matching_results_connector.tsv"

scp -o IdentitiesOnly=yes -i "$KEY" \
  "$EC2:~/ber/output/candidate_pairs.tsv" \
  "$ROOT/submit_folder/candidate_pairs_connector.tsv"

scp -o IdentitiesOnly=yes -i "$KEY" \
  "$EC2:~/ber/artifacts/runs.jsonl" \
  "$ROOT/submit_folder/runs_final.jsonl"
```

Then, still in **Mac Terminal**, assemble and verify the required archive:

```bash
ROOT="/Users/pocketfm/Desktop/amazon_ML/Working Folder"
cd "$ROOT"

mkdir -p final_submission/output
mkdir -p final_submission/code/business_entity_resolution/notebooks

cp submit_folder/matching_results_connector.tsv \
  final_submission/output/matching_results.tsv
cp submit_folder/candidate_pairs_connector.tsv \
  final_submission/output/candidate_pairs.tsv
cp -R src/. final_submission/code/business_entity_resolution/src/
cp requirements.txt final_submission/code/business_entity_resolution/requirements.txt
cp notebooks/NB02_metric_and_splits.ipynb \
  notebooks/NB09_submission.ipynb \
  final_submission/code/business_entity_resolution/notebooks/

python3 student_resource/utils/validate_submission.py \
  --matching final_submission/output/matching_results.tsv \
  --candidate final_submission/output/candidate_pairs.tsv \
  --test-dir student_resource/dataset/test

cd final_submission
zip -r ../WinKing_submission_connector.zip output code Documentation_template.md
cd ..
unzip -l WinKing_submission_connector.zip
```

The final ZIP must contain exactly the final matching file, the matching candidate file,
the runnable source/notebooks/requirements, and the filled methodology document.
