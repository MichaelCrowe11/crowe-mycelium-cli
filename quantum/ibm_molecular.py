"""IBM Quantum molecular ground-state pipeline (kept honestly separate from LLM training).

What this does:
  - Builds a small-molecule electronic-structure problem (PySCF).
  - Maps it to qubits (Jordan-Wigner).
  - Runs VQE to estimate the ground-state energy.
  - Backend: Aer simulator by default; real IBM Quantum hardware if
    IBM_QUANTUM_TOKEN is set in the environment.

What this DOES NOT do:
  - Speed up LLM training. (Quantum hardware has no algorithm for backprop.)
  - Run anything larger than ~12 qubits on real hardware usefully today.

Useful molecules in scope:
  - H2, LiH                : full-basis, works perfectly
  - serotonin / psilocin   : require active-space reduction (4-6 spatial orbitals)
                             and remain noisy on near-term hardware

Results go to data/quantum_results/<molecule>_<timestamp>.json so the eval
bench and downstream training can consume them as factual reference points.

Install: pip install -r quantum/requirements-quantum.txt
"""
import argparse, json, os
from datetime import datetime
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
DEFAULT_OUT = REPO_ROOT / "data" / "quantum_results"

MOLECULES = {
    "h2":  "H 0 0 0; H 0 0 0.735",
    "lih": "Li 0 0 0; H 0 0 1.5949",
    "h2o": "O 0 0 0; H 0 0.757 0.586; H 0 -0.757 0.586",
}


def build_problem(atom_spec: str, basis: str = "sto3g"):
    from qiskit_nature.units import DistanceUnit
    from qiskit_nature.second_q.drivers import PySCFDriver
    driver = PySCFDriver(
        atom=atom_spec, unit=DistanceUnit.ANGSTROM, basis=basis,
    )
    return driver.run()


def make_solver(num_qubits: int, backend: str):
    from qiskit.circuit.library import EfficientSU2
    from qiskit_algorithms import VQE
    from qiskit_algorithms.optimizers import SLSQP
    ansatz = EfficientSU2(num_qubits=num_qubits, reps=1)

    if backend == "ibm_quantum":
        token = os.environ.get("IBM_QUANTUM_TOKEN")
        if not token:
            raise SystemExit("Set IBM_QUANTUM_TOKEN to use real hardware.")
        from qiskit_ibm_runtime import QiskitRuntimeService, EstimatorV2 as Estimator
        service = QiskitRuntimeService(channel="ibm_quantum", token=token)
        instance = os.environ.get("IBM_QUANTUM_INSTANCE", "ibm-q/open/main")
        backend_obj = service.least_busy(operational=True, simulator=False, min_num_qubits=num_qubits)
        print(f"[quantum] IBM backend: {backend_obj.name}")
        estimator = Estimator(mode=backend_obj)
    else:
        from qiskit.primitives import Estimator
        estimator = Estimator()

    return VQE(estimator, ansatz, SLSQP(maxiter=200))


def solve(molecule: str, basis: str, backend: str):
    from qiskit_nature.second_q.mappers import JordanWignerMapper
    from qiskit_nature.second_q.algorithms import GroundStateEigensolver

    problem = build_problem(MOLECULES[molecule], basis=basis)
    mapper = JordanWignerMapper()
    num_qubits = problem.num_spatial_orbitals * 2

    vqe = make_solver(num_qubits, backend)
    solver = GroundStateEigensolver(mapper, vqe)
    result = solver.solve(problem)

    return {
        "molecule": molecule,
        "geometry": MOLECULES[molecule],
        "basis": basis,
        "mapper": "JordanWigner",
        "method": "VQE",
        "ansatz": "EfficientSU2(reps=1)",
        "optimizer": "SLSQP",
        "backend": backend,
        "num_qubits": num_qubits,
        "ground_state_energy_hartree": float(result.total_energies[0]),
        "computed_at": datetime.now().isoformat(timespec="seconds"),
    }


def main(args):
    if args.molecule not in MOLECULES:
        raise SystemExit(f"Unknown molecule {args.molecule!r}. "
                         f"Available: {list(MOLECULES)}")
    out_dir = Path(args.out)
    out_dir.mkdir(parents=True, exist_ok=True)
    result = solve(args.molecule, args.basis, args.backend)
    stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    fp = out_dir / f"{args.molecule}_{args.backend}_{stamp}.json"
    fp.write_text(json.dumps(result, indent=2))
    print(json.dumps(result, indent=2))
    print(f"[quantum] wrote {fp}")


if __name__ == "__main__":
    p = argparse.ArgumentParser()
    p.add_argument("--molecule", default="h2", choices=list(MOLECULES))
    p.add_argument("--basis", default="sto3g")
    p.add_argument("--backend", default="simulator", choices=["simulator", "ibm_quantum"])
    p.add_argument("--out", default=str(DEFAULT_OUT))
    main(p.parse_args())
