import json
import logging
from datetime import datetime
from typing import Optional

import requests
import tzlocal
from requests_toolbelt import MultipartEncoder

from domain.scrap_result import LoginResult

DATETIME_FORMAT = "%d-%m-%Y %H:%M:%S"


class F24APIClient:
    BASE_URL = "https://freedom24.com"

    def __init__(self):
        self._session = None
        self._user_info = None
        self._log = logging.getLogger(__name__)

    def _execute_request(
            self, path: str, method: str, data: str, headers: Optional[dict] = None
    ) -> dict:
        response = self._session.request(
            method, self.BASE_URL + path, data=data, headers=headers
        )

        if response.ok:
            return response.json()

        self._log.error("Error Status Code:", response.status_code)
        self._log.error("Error Response Body:", response.text)
        raise Exception("There was an error during the request")

    def _post_request(self, path: str, data: str, headers: Optional[dict] = None) -> dict:
        return self._execute_request(path, "POST", data=data, headers=headers)

    def _multi_part(self, path: str, data: dict) -> requests.Response:
        multipart_data = MultipartEncoder(
            fields=data
        )

        return self._session.post(
            self.BASE_URL + path, data=multipart_data, headers={'Content-Type': multipart_data.content_type}
        )

    def _request_login(self, username: str, password: str, user_id: Optional[str] = None) -> requests.Response:
        timezone = {
            'timezone': tzlocal.get_localzone_name(),
            "offset": str(datetime.now().astimezone().utcoffset().seconds // 3600 * -1)
        }

        data = {
            "login": username,
            "password": password,
            "rememberMe": "true",
            "mode": "regular",
            "timezone": json.dumps(timezone)
        }

        if user_id:
            data["userId"] = user_id
        else:
            data["getAccounts"] = "true"

        return self._multi_part("/authentication/ajax-check-login-password", data=data)

    def login(self, username: str, password: str) -> dict:
        self._session = requests.Session()
        self._session.headers["Origin"] = self.BASE_URL

        first_login_response = self._request_login(username, password)

        if first_login_response.ok:
            response_body = first_login_response.json()
            if "error" in response_body:
                error = response_body["error"].strip()
                if "Incorrect e-mail or password" in error:
                    return {"result": LoginResult.INVALID_CREDENTIALS}

                else:
                    return {"result": LoginResult.UNEXPECTED_ERROR, "message": error}

            else:
                self._user_info = response_body

        else:
            return {"result": LoginResult.UNEXPECTED_ERROR,
                    "message": f"Got unexpected response code {first_login_response.status_code}"}

        user_id = None
        accounts = self._user_info["accounts"]
        for acc in accounts:
            if acc["account_type"] == "brokerage":
                user_id = str(acc["user_id"])
                break

        login_response = self._request_login(username, password, user_id)

        if login_response.ok:
            response_body = login_response.json()
            if "error" in response_body:
                error = response_body["error"].strip()
                if "Incorrect e-mail or password" in error:
                    return {"result": LoginResult.INVALID_CREDENTIALS}

                else:
                    return {"result": LoginResult.UNEXPECTED_ERROR, "message": error}

            else:
                if (response_body["success"]
                        and response_body["logged"]
                        and response_body["SID"]):
                    return {"result": LoginResult.CREATED}

                self._log.error(response_body)
                return {"result": LoginResult.UNEXPECTED_ERROR,
                        "message": "Got unexpected response"}

        else:
            return {"result": LoginResult.UNEXPECTED_ERROR,
                    "message": f"Got unexpected response code {first_login_response.status_code}"}

    def get_user_info(self) -> dict:
        return self._user_info

    def get_cash_flows(self) -> dict:
        data = {
            "q": '{"cmd":"getUserCashFlows","params":{"filter":{}}}'
        }
        return self._multi_part("/api", data=data).json()

    def get_positions(self, user_id: str) -> dict:
        data = 'q={"cmd":"getUserPositions","params":{"requestedUserId":' + user_id + '}}'
        headers = {
            "Content-Type": "application/x-www-form-urlencoded; charset=UTF-8"
        }
        return self._post_request("/api", data=data, headers=headers)

    def get_trades(self, user_id: str) -> dict:
        data = f"user_id={user_id}"
        headers = {
            "Content-Type": "application/x-www-form-urlencoded"
        }
        return self._post_request("/portfolios/ajax-get-trades/", data=data, headers=headers)

    def get_off_balance(self) -> dict:
        data = {
            "q": '{"cmd":"getOffBalanceAssets","params":{}}'
        }
        return self._multi_part("/api?cmd=getOffBalanceAssets", data=data).json()

    def switch_user(self, trader_systems_id: str):
        data = 'q={"cmd":"switchToConnectedUser","params":{"trader_systems_id":"' + trader_systems_id + '"}}'
        headers = {
            "Content-Type": "application/x-www-form-urlencoded; charset=UTF-8"
        }
        return self._post_request("/api?cmd=switchToConnectedUser", data=data, headers=headers)
