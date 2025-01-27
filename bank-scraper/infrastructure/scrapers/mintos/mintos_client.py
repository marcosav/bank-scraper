import os
from typing import Union, Optional

import requests
from cachetools import TTLCache, cached

from domain.scrap_result import LoginResult


class MintosAPIClient:
    BASE_URL = "https://www.mintos.com"
    BASE_API_URL = f"{BASE_URL}/webapp/api"
    USER_PATH = f"{BASE_API_URL}/en/webapp-api/user"

    def __init__(self):
        self.__session = requests.Session()

    def __execute_request(
            self,
            path: str,
            method: str,
            body: Optional[dict] = None,
            params: Optional[dict] = None,
    ) -> Union[dict, str]:
        response = self.__session.request(
            method, self.BASE_API_URL + path, json=body, params=params
        )

        if response.ok:
            return response.json()

        print("Error Status Code:", response.status_code)
        print("Error Response Body:", response.text)
        raise Exception("There was an error during the request")

    def __get_request(
            self, path: str, params: dict = None
    ) -> Union[dict, str]:
        return self.__execute_request(path, "GET", params=params)

    def __post_request(
            self, path: str, body: dict
    ) -> Union[dict, requests.Response]:
        return self.__execute_request(path, "POST", body=body)

    async def login(self, username: str, password: str) -> dict:

        from selenium.common import TimeoutException
        from selenium.webdriver.common.by import By
        from selenium.webdriver.common.keys import Keys
        from selenium.webdriver.firefox.options import Options
        from selenium.webdriver.firefox.service import Service
        from selenium.webdriver.support import expected_conditions as EC
        from selenium.webdriver.support.ui import WebDriverWait
        from seleniumwire import webdriver

        from infrastructure.scrapers.mintos.recaptcha_solver_selenium import RecaptchaSolver

        geckodriver_path = os.getenv("GECKODRIVER_PATH")
        geckodriver_logs_path = os.getenv("GECKODRIVER_LOGS_PATH", "geckodriver.log")

        driver = None

        if geckodriver_path:
            service = Service(executable_path=geckodriver_path, log_path=geckodriver_logs_path)
        else:
            service = Service()

        options = Options()
        options.add_argument("--headless")

        try:
            driver = webdriver.Firefox(options=options, service=service)

            driver.get(f"{self.BASE_URL}/en/login/")

            wait = WebDriverWait(driver, 5)
            wait.until(EC.element_to_be_clickable((By.ID, "login-username")))

            username_input = driver.find_element(By.ID, "login-username")
            username_input.send_keys(username)

            password_input = driver.find_element(By.ID, "login-password")
            password_input.send_keys(password)

            password_input.send_keys(Keys.RETURN)

            wait = WebDriverWait(driver, 4)
            try:
                wait.until(EC.url_contains("overview"))
            except TimeoutException:
                print("Not redirecting to overview page, checking recaptcha.")
                recaptcha_solver = RecaptchaSolver(driver, 10)
                await recaptcha_solver.solve_audio_captcha()

            driver.wait_for_request(self.USER_PATH, timeout=10)

            user_request = next(x for x in driver.requests if self.USER_PATH in x.url)

            self.__session.headers["Cookie"] = user_request.headers["Cookie"]

            return {"result": LoginResult.CREATED}

        except Exception as e:
            print(f"An error occurred while logging in: {e}")
            raise

        finally:
            if driver:
                driver.quit()

    @cached(cache=TTLCache(maxsize=1, ttl=120))
    def get_user(self) -> dict:
        return self.__get_request("/en/webapp-api/user")

    @cached(cache=TTLCache(maxsize=1, ttl=120))
    def get_overview(self, wallet_currency_id) -> dict:
        return self.__get_request(f"/marketplace-api/v1/user/overview/currency/{wallet_currency_id}")

    @cached(cache=TTLCache(maxsize=1, ttl=120))
    def get_net_annual_returns(self, wallet_currency_id) -> dict:
        return self.__get_request(
            f"/en/webapp-api/user/overview-net-annual-returns?currencyIsoCode={wallet_currency_id}")

    @cached(cache=TTLCache(maxsize=1, ttl=120))
    def get_portfolio(self, wallet_currency_id) -> dict:
        return self.__get_request(f"/marketplace-api/v1/user/overview/currency/{wallet_currency_id}/portfolio-data")
