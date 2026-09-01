# Deployment

The public site is hosted by GitHub Pages from the `main` branch and the repository root. The repository root forwards to the dashboard in `dashboard/`, so both links are useful:

- [Repository root](https://jaronkbragg7337.github.io/MachineManager-RevenueLab/)
- [Mission Control](https://jaronkbragg7337.github.io/MachineManager-RevenueLab/dashboard/)

Publishing a new sanitized `dashboard/data/*.json` projection and pushing it to `main` refreshes the public page. The page is static and no-login; the local manager remains the source that produces the projection.

The first deployment uses GitHub’s branch source because this repository does not require a build step. CI still runs the Python, JavaScript, and public-data checks on pushes and pull requests.
