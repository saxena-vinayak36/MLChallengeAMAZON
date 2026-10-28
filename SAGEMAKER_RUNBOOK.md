# Running the Pipeline on Amazon SageMaker AI

> **Current project status (2026-09-27): EC2 is the primary execution runtime.** The
> challenge is currently running on `ber-runner` under `~/ber` with Python 3.12. This
> document remains the SageMaker alternative; do not follow its SageMaker launch steps
> while using EC2. On the 8 GiB EC2 machine, run only the memory-bounded S3 miner and
> S4 pilot/blocking notebooks. Full S4/S5+ work still requires the larger resources
> listed below.

**Written for:** future me, opening this repo on a fresh SageMaker Studio JupyterLab
space or a SageMaker Notebook Instance for the first time.

Two SageMaker surfaces exist, and the AWS docs and console both call them "SageMaker AI"
today. Pick one; do not mix them.

| | **SageMaker Studio (JupyterLab spaces)** ← preferred | **SageMaker Notebook Instances** |
|---|---|---|
| What it is | The current-generation managed JupyterLab, launched inside a Studio *Domain*. Same JupyterLab UI, cleaner start/stop model. | Older single-VM notebooks. Still fully supported; simpler mental model. |
| When to prefer | Interactive iteration, easy instance swap. | Long-running batches when you want one persistent EBS volume. |

The rest of this file uses **Studio JupyterLab**. The `Notebook Instances` variant is
almost the same — the notes at the bottom flag the small differences.

---

## 0. One-time account setup

1. **Enable the SageMaker AI service** and create a Studio Domain (Console → Amazon
   SageMaker AI → *Domains* → *Create Domain* → "Quick setup" is fine for a single-user
   dev domain; use "Standard setup" if you need to attach a specific IAM role).
2. **Request a GPU quota bump** before you need one. Console → Service Quotas → *Amazon
   SageMaker* → search for `Studio JupyterLab Apps running on ml.g5.2xlarge instance`
   (or `ml.g4dn.xlarge`) → *Request quota increase*. New accounts default to zero for
   G-family; approval can take a day, which on a tight timeline silently deletes the
   neural stage — this is **D-14**'s revisit clause made concrete.

## 1. Start a JupyterLab Space

Studio → *Applications* → *JupyterLab* → *Create JupyterLab space*.

* **Instance:** start on the cheap side and swap up when a stage needs it.
  * **CPU / RAM stages** (blocking, features, LightGBM): `ml.r7i.4xlarge` or
    `ml.m7i.4xlarge` (16 vCPU, ≥64 GB).
  * **GPU stages** (embedder, reranker): `ml.g5.2xlarge` (1× A10G, 24 GB).
  * **Everything else** (setup, EDA, metric, splits, decision layer, packaging):
    `ml.t3.large` is plenty.
  You can stop the space and reopen it on a different instance without losing files on
  the EBS volume.
* **Storage:** 300 GB gp3 is enough for the dataset (2.3 GB raw) plus parquet
  intermediates, model checkpoints and a buffer.
* Open the space.

## 2. Get the code into the space

Two options; pick one and stick with it.

**A. `git clone` from a terminal** — best when the project is on GitHub/GitLab.

```bash
cd ~
git clone https://<git-host>/<user>/<repo>.git ber
cd ber
```

If the repo is private, add a GitHub personal-access token to Studio via *Git → Manage
credentials* first, or use SSH by pasting the deploy key into your fork.

**B. *Upload* button** — best for a one-off transfer or when the code is not in git.

In the JupyterLab file browser, click the **⬆︎ Upload** icon and drop the whole
`Working Folder/` in. Uploads land at `~/<name>/`.

Either way, the code should end up at `~/ber` (or override with `BER_ROOT`, see §4).

## 3. Get the dataset in

The `student_resource/dataset/` folder is 2.3 GB. Two ways in:

**A. `aws s3 cp` from a bucket you own** — recommended once you've done this more than
twice.

```bash
# One-off from your local machine, so the dataset stays close to SageMaker:
aws s3 cp --recursive "student_resource/dataset" s3://<your-bucket>/ber/dataset/

# In SageMaker (each time you spin up a fresh space):
mkdir -p ~/ber/student_resource/dataset
aws s3 cp --recursive s3://<your-bucket>/ber/dataset/ ~/ber/student_resource/dataset/
```

**B. Upload button** — fine for the first time. JupyterLab handles the 2.3 GB stream
with progress; leave the tab open until it finishes.

## 4. Install the environment

Open a *Terminal* (File → New → Terminal) in the space:

```bash
cd ~/ber

# Optional: point BER_ROOT somewhere other than the SageMaker default the code auto-detects
# (~/SageMaker/ber for classic notebook instances, ~/ber for Studio JupyterLab).
export BER_ROOT="$HOME/ber"

# Pinned deps for the current stage. requirements.txt grows stage-by-stage —
# re-run this after every git pull.
pip install --quiet -r requirements.txt
```

Studio JupyterLab persists the pip cache and site-packages on the space's EBS volume,
so this only needs to run again after `pip install`-ing something new.

**If pip is slow inside SageMaker**, use `--no-cache-dir` and, when you install
`torch`, pin to a CUDA-matched wheel:

```bash
pip install --no-cache-dir torch==2.5.1 --index-url https://download.pytorch.org/whl/cu121
```

## 5. Run the notebooks

Open `notebooks/NB00_setup.ipynb`. Choose the kernel **`Python 3 (ipykernel)`**
(top-right corner). Run all cells; the config cell at the top will detect SageMaker
(`ON_SAGEMAKER=True`) and set paths automatically.

Run the numbered notebooks in order. Every notebook writes its intermediate artifacts
to `~/ber/artifacts/`, so a later notebook can start from disk without re-executing an
earlier one.

## 6. Long-running jobs — three options

1. **In-notebook.** Simple, but the run dies if the JupyterLab tab or the space is
   closed. Fine for anything under an hour.
2. **`nohup` in a terminal** for a single long job:

   ```bash
   cd ~/ber
   nohup jupyter nbconvert --to notebook --execute notebooks/NB06_model_gbm.ipynb \\
       --output NB06_model_gbm.executed.ipynb > logs/NB06.log 2>&1 &
   ```

   The space itself still needs to stay up; stop-and-resume is fine, the process keeps
   running as long as the space is running.
3. **Amazon SageMaker JupyterLab Notebook Scheduler** — the extension bundled with
   Studio. Right-click a notebook → *Create notebook job*. Runs the notebook as an
   ephemeral training job on a chosen instance; you can close the Studio tab. Best for
   the ~4 h cross-encoder fine-tune when the time comes.

## 7. Watch the bill

* Stop the space when you're done for the day (Studio → *Applications* → *JupyterLab*
  → *Stop*). A running `ml.g5.2xlarge` costs ~$1.21/h; a stopped one costs only the
  EBS storage.
* `ml.t3.large` is fine to leave running for interactive work — a few cents an hour.
* Delete the EBS volume with the space (from the domain page) once the project is done.

---

## Differences on classic SageMaker Notebook Instances

If your account gives you `Notebook Instances` instead of Studio:

* Create the instance from Console → SageMaker AI → *Notebook* → *Notebook instances*.
  You can pass a public git repo URL directly ("Clone a public Git repository to this
  notebook instance only"), or attach a lifecycle-configuration script that clones a
  private repo and runs `pip install -r requirements.txt` on start.
* Default project path is `/home/ec2-user/SageMaker/` (this is what the config cell's
  `sagemaker_root` default already points at).
* Kernel selection: pick `conda_python3`, not `Python 3 (ipykernel)`.
* Everything else — instance sizing, S3 sync, `nohup` for long jobs — is identical.

Sources:
- [Configure a Notebook Instance / clone git — AWS docs](https://docs.aws.amazon.com/sagemaker/latest/dg/nbi-add-external.html)
- [Amazon SageMaker Studio JupyterLab (2023 launch note)](https://aws.amazon.com/about-aws/whats-new/2023/11/amazon-sagemaker-studio-fully-managed-notebooks-jupyterlab)
- [SageMaker JupyterLab notebook scheduler blog](https://aws.amazon.com/blogs/machine-learning/schedule-your-notebooks-from-any-jupyterlab-environment-using-the-amazon-sagemaker-jupyterlab-extension/)
- [Cloning a git repo in a SageMaker notebook instance](https://www.c-sharpcorner.com/article/how-to-clone-git-repository-in-aws-notebook-instances/)
- [Lifecycle-configuration scripts for git access — re:Post](https://repost.aws/questions/QUhTwl-BZURCGatI4Rm9fFqg/lifecycle-scripts-to-access-the-notebook-instance-git-repository)
