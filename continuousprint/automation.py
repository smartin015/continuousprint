from io import StringIO
import re
from asteval import Interpreter


def getInterpreter(symbols):
    out = StringIO()
    err = StringIO()
    interp = Interpreter(writer=out, err_writer=err)
    # Merge in so default symbols (e.g. exceptions) are retained
    for k, v in symbols.items():
        interp.symtable[k] = v
    return interp, out, err


def genEventScript(automation: list, interp=None, logger=None) -> str:
    result = []
    for script, preprocessor in automation:
        procval = True
        if preprocessor is not None and preprocessor.strip() != "":
            procval = interp(preprocessor)
            if logger:
                logger.info(
                    f"EventHook preprocessor: {preprocessor}\nResult: {procval}"
                )

        if procval is None or procval is False:
            continue
        elif procval is True:
            formatted = script
        elif type(procval) is dict:
            if logger:
                logger.info(f"Appending script using formatting data {procval}")
            formatted = script.format(**procval)
        else:
            raise Exception(
                f"Invalid return type {type(procval)} for peprocessor {preprocessor}"
            )

        leftovers = re.findall(r"\{.*?\}", formatted)
        if len(leftovers) > 0:
            ppname = " (preprocessed)" if e.preprocessor is not None else ""
            raise Exception(f"Unformatted placeholders in script{ppname}: {leftovers}")
        result.append(formatted)
    return "\n".join(result)
