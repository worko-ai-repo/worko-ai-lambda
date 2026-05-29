"""CTC and experience compatibility checker."""

from typing import Dict, Union


def check_exp_ctc(inpute: Dict[str, Union[float, Dict]]) -> Dict[str, Union[bool, str]]:
    """Check if candidate's CTC and experience match job requirements.
    
    Args:
        inpute: Dict containing:
            - cv_ctc: Candidate's current CTC in LPA
            - cv_exp: Candidate's total experience in years
            - jd_ctc: Dict with 'min' and 'max' CTC range
            - jd_exp: Dict with 'min' and 'max' experience range
    
    Returns:
        Dict with keys:
            - ctc: False or "above" if overqualified
            - experience: False or "above"/"below" if mismatched
            - Explanation: Combined explanation string or False
    """
    # Convert all numeric inputs to float safely
    cv_ctc = float(inpute["cv_ctc"])
    cv_exp = float(inpute["cv_exp"])

    jd_ctc = inpute["jd_ctc"]
    jd_exp = inpute["jd_exp"]

    jd_ctc_min = float(jd_ctc["min"])
    jd_ctc_max = float(jd_ctc["max"])
    jd_exp_min = float(jd_exp["min"])
    jd_exp_max = float(jd_exp["max"])

    ECTC = cv_ctc * 1.25

    result = {"ctc": False, "experience": False, "Explanation": False}

    explanations = []  # collect multiple messages
    min_threshhold_ctc = jd_ctc_min * 0.7
    max_threshhold_ctc = jd_ctc_max * 0.6
    
    if jd_exp_max <= 4:
        print(f'exp less the 4 jd exp {jd_exp_max} cv exp {cv_exp}')

        if cv_exp > (jd_exp_max * 1.6):  # (overqualified exp)
            print("statment 1")

            msg = (
                f"You are overqualified for this role in terms of experience. your total experience is"
                f"{cv_exp} years But this role expected maximum {jd_exp_max} years of experience ."
            )

            result["experience"] = "above"

            explanations.append(msg)

    elif jd_exp_min * 0.3 >= 3:  # if  30% of minimum exp is grater then 3   (underqualified exp)
        print("Min exp 30% is Greater then 3")
        print("1")
        
        if jd_exp_min - cv_exp > 3:  # check if candidate exp is 3 years less then min_exp_jd
            print("statment 2")
            print(f"jd_mim {jd_exp_min} cv exp {cv_exp}")

            msg = (
                f"You are underqualified in terms of experience your total experience is "
                f"{cv_exp} years But this role expected minimum of {jd_exp_min} years of experience ."
            )

            result["experience"] = "below"  # True

            explanations.append(msg)

    elif cv_exp < (jd_exp_min * 0.7):
        print("statment 3")
        msg = (
            f"You are underqualified in terms of experience your total experience is "
            f"{cv_exp} years But this role expected minimum of {jd_exp_min} years of experience ."
        )
        result["experience"] = "below"  # True
        explanations.append(msg)

    if jd_exp_max * 0.4 > 4:  # if  40% of maximum exp is grater then 4  (overqualified exp)
        print("max exp 40% is Greater then 4")
        
        if cv_exp - jd_exp_max > 4:  # check if candidate exp is 4 years greater then max_jd_exp
            print(f"jd_mx {jd_exp_max} cv exp {cv_exp}")
            print("statment 4")

            msg = (
                f"You are overqualified for this role in terms of experience. your total experience is "
                f"{cv_exp} years which exceeds job?Ts maximum required experience is {jd_exp_max} years."
            )

            result["experience"] = "above"  # True
            explanations.append(msg)

    elif cv_exp > jd_exp_max * 1.4 and jd_exp_max > 4:
        print("statment 5")

        msg = (
            f"You are overqualified for this role in terms of experience. your total experience is "
            f"{cv_exp} years which exceeds job?Ts maximum required experience is {jd_exp_max} years."
        )
        result["experience"] = "above"  # True

        explanations.append(msg)

    if ECTC > jd_ctc_max * 1.2 and (jd_ctc_max * 1.2) > 10:  # CTC logic
        print("statment 6")
        msg = (
            f"You are overqualified in terms of compensation, as your current CTC "
            f"{cv_ctc} LPA and maximum offered by this role is {jd_ctc_max} LPA."
        )
        result["ctc"] = "above"  # True
        explanations.append(msg)

    if ECTC > jd_ctc_max * 1.3 and (jd_ctc_max * 1.2) < 10:  # CTC logic
        print("statment 7")
        msg = (
            f"You are overqualified in terms of compensation, as your current CTC "
            f"{cv_ctc} LPA and maximum offered by this role is {jd_ctc_max} LPA."
        )
        result["ctc"] = "above"  # True

        explanations.append(msg)

    # ---- Combine Explanations ----
    if explanations:
        if len(explanations) > 1:
            result["Explanation"] = ", ".join(explanations[:-1]) + " and " + explanations[-1]
        else:
            result['Explanation'] = explanations[0]
    else:
        result["Explanation"] = False

    return result
