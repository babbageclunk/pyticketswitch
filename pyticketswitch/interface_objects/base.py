import logging

from pyticketswitch import settings as default_settings
from pyticketswitch.interface import CoreAPI
from pyticketswitch.util import (
    resolve_boolean, format_price_with_symbol,
    to_float_or_none,
)

logger = logging.getLogger(__name__)


class InterfaceObject(object):
    """Superclass for all objects that will perform API operations.

    The class should not be instantiated directly, it is designed to
    be subclassed. Contains a number of internal methods that provide
    standard functionality for API operations.

    Subclasses of this object should call the constructor of this
    object.

    Args:
        username (string): TSW user
        password (string): password for TSW user
        url (string): TSW API URL
        accept_language (string): user's HTTP Accept-Language header
        api_request_timeout (int): API timeout in seconds
        no_time_descr (string): text to use if no time is returned
            by the API for a performance
        default_concession_descr (string): text to use if no description
            is returned by the API for a concession
        remote_ip (string): user's IP address (internal use)
        remote_site (string): domain of the user request (internal use)
        ext_start_session_url (string): URL for start_session (internal user)

    """

    CRYPTO_PREFIX = 'CRYPTO_BLOCK'
    USERNAME_PREFIX = 'USERNAME'
    RUNNING_USER_PREFIX = 'RUNNING_USER'

    def __init__(self, **kwargs):

        self._session = None
        self._core_api = None
        self.settings = self._get_settings()
        self._session_store = {}

        if 'session' in kwargs:
            self._session = kwargs.pop('session')

        if '_core_api' in kwargs:
            self._core_api = kwargs.pop('_core_api')

        if '_settings' in kwargs:
            self.settings = kwargs.pop('_settings')

        if '_session_store' in kwargs:
            self._session_store = kwargs.pop('_session_store')

        if kwargs:
            self._configure(**kwargs)

    def _get_settings(
        self, username=None, password=None, url=None,
        no_time_descr=None, api_request_timeout=None,
        default_concession_descr=None, remote_ip=None,
        remote_site=None, accept_language=None,
        ext_start_session_url=None
    ):
        return {
            'username': username,
            'password': password,
            'remote_ip': remote_ip,
            'remote_site': remote_site,
            'accept_language': accept_language,
            'url': url,
            'ext_start_session_url': ext_start_session_url,
            'api_request_timeout': api_request_timeout,
            'no_time_descr': no_time_descr,
            'default_concession_descr': default_concession_descr,
        }

    def _configure(
        self, username=None, password=None, url=None,
        no_time_descr=None, api_request_timeout=None,
        default_concession_descr=None, remote_ip=None,
        remote_site=None, accept_language=None,
        ext_start_session_url=None
    ):

        if (not username) and remote_ip and remote_site:
            username = self._get_cached_username(
                remote_ip=remote_ip,
                remote_site=remote_site
            )

        if (
            (
                'username' in self.settings and
                self.settings['username'] and
                username != self.settings['username']
            ) or
            (
                'remote_ip' in self.settings and
                self.settings['remote_ip'] and
                remote_ip != self.settings['remote_ip']
            ) or
            (
                'remote_site' in self.settings and
                self.settings['remote_site'] and
                remote_site != self.settings['remote_site']
            )
        ):
            self._clear_crypto_blocks()

        if not url:
            url = default_settings.API_URL

        if not ext_start_session_url:
            ext_start_session_url = default_settings.EXT_START_SESSION_URL

        if not api_request_timeout:
            api_request_timeout = default_settings.API_REQUEST_TIMEOUT

        if not no_time_descr:
            no_time_descr = default_settings.NO_TIME_DESCR

        if not default_concession_descr:
            default_concession_descr = (
                default_settings.DEFAULT_CONCESSION_DESCR
            )

        self.settings = self._get_settings(
            username=username, password=password,
            url=url, no_time_descr=no_time_descr,
            api_request_timeout=api_request_timeout,
            default_concession_descr=default_concession_descr,
            remote_ip=remote_ip,
            remote_site=remote_site,
            accept_language=accept_language,
            ext_start_session_url=ext_start_session_url
        )

        self._core_api = CoreAPI(
            username=username,
            password=password,
            url=url,
            remote_ip=remote_ip,
            remote_site=remote_site,
            accept_language=accept_language,
            ext_start_session_url=ext_start_session_url,
            api_request_timeout=api_request_timeout
        )

    def get_core_api(self):
        return self._core_api

    def set_session(self, session):
        self._session = session

    def _password_is_set(self):

        if self.settings.get('password'):
            return True
        else:
            return False

    def _start_session(self):
        crypto_block = self.get_core_api().start_session()

        username = self.get_core_api().username

        if (
            not self.settings['username'] or
            username != self.settings['username']
        ):

            remote_ip = self.settings['remote_ip']
            remote_site = self.settings['remote_site']

            self.settings['username'] = username
            self._set_cached_username(
                username=username,
                remote_ip=remote_ip,
                remote_site=remote_site
            )

            self._set_cached_running_user(
                username=username,
                running_user=self.get_core_api().running_user,
            )

        if crypto_block:
            self._set_crypto_block(
                crypto_block=crypto_block,
                method_name='start_session'
            )

        return crypto_block

    def get_username(self):

        if not self.settings['username']:

            remote_ip = self.settings['remote_ip']
            remote_site = self.settings['remote_site']

            username = self._get_cached_username(
                remote_ip=remote_ip,
                remote_site=remote_site
            )

            if not username:
                self._start_session()

        return self.settings['username']

    def _get_running_user(self):
        if not self.get_core_api().running_user:

            running_user = self._get_cached_running_user(
                username=self.get_username()
            )

            if running_user:
                self.get_core_api().running_user = running_user
            else:
                self._start_session()

        return self.get_core_api().running_user

    def get_restrict_group(self):
        return self._get_running_user().restrict_group

    def get_default_language_code(self):
        return self._get_running_user().default_lang_code

    def get_content_language(self):
        return self.get_core_api().content_language

    def _store_data(self, key, data, save_session=True):

        logger.debug('_store_data, key: %s, data: %s', key, data)

        self._session_store[key] = data

        if self._session is not None:
            self._session[key] = data

            if save_session and hasattr(self._session, 'save'):
                self._session.save()

    def _retrieve_data(self, key):

        data = self._session_store.get(key, None)

        if not data and self._session is not None:
            data = self._session.get(key)

        logger.debug('_retrieve_data, key: %s, data: %s', key, data)

        return data

    def _get_username_session_key(self, remote_ip, remote_site):
        return '{0}_{1}_{2}'.format(
            self.USERNAME_PREFIX, remote_ip, remote_site
        )

    def _get_cached_username(
        self, remote_ip, remote_site
    ):
        key = self._get_username_session_key(
            remote_ip=remote_ip,
            remote_site=remote_site
        )

        return self._retrieve_data(key)

    def _set_cached_username(
        self, username, remote_ip, remote_site
    ):
        key = self._get_username_session_key(
            remote_ip=remote_ip,
            remote_site=remote_site
        )

        self._store_data(key=key, data=username)

    def _get_running_user_session_key(self, username):
        return '{0}_{1}'.format(
            self.RUNNING_USER_PREFIX, username
        )

    def _get_cached_running_user(self, username):

        key = self._get_running_user_session_key(
            username=username,
        )

        return self._retrieve_data(key)

    def _set_cached_running_user(self, username, running_user):

        key = self._get_running_user_session_key(
            username=username,
        )

        self._store_data(key=key, data=running_user)

    def _get_crypto_session_key(self, username, method_name):
        return '{0}_{1}_{2}'.format(
            self.CRYPTO_PREFIX, username, method_name
        )

    def _clear_crypto_blocks(self):

        logger.debug('_clear_crypto_blocks called')

        for key in self._session_store.keys():
            if key.startswith(self.CRYPTO_PREFIX):
                del self._session_store[key]

        if self._session is not None:

            if hasattr(self._session, 'flush_crypto_blocks'):
                self._session.flush_crypto_blocks()
            else:
                for key in self._session.keys():
                    if key.startswith(self.CRYPTO_PREFIX):
                        del self._session[key]

    def get_crypto_block(
        self, method_name, password_required=True
    ):

        crypto_block = None

        if (
            password_required or (
                not password_required and not self._password_is_set()
            )
        ):
            if not self.settings.get('username', False):
                start_session_crypto = self._start_session()
            else:
                start_session_crypto = None

            session_key = self._get_crypto_session_key(
                username=self.settings['username'],
                method_name=method_name
            )

            crypto_block = self._retrieve_data(session_key)

            if not crypto_block and method_name == 'start_session':

                if start_session_crypto:
                    crypto_block = start_session_crypto
                else:
                    crypto_block = self._start_session()

        return crypto_block

    def _set_crypto_block(self, crypto_block, method_name):

        session_key = self._get_crypto_session_key(
            username=self.settings['username'], method_name=method_name
        )

        self._store_data(key=session_key, data=crypto_block)

    def _get_crypto_object_key(
        self, username, method_name, interface_object
    ):

        return '{0}_{1}'.format(
            self._get_crypto_session_key(
                username=username, method_name=method_name
            ), interface_object._get_cache_key()
        )

    def _set_crypto_for_objects(
        self, crypto_block, method_name, interface_objects
    ):

        for i, obj in enumerate(interface_objects):
            key = self._get_crypto_object_key(
                username=self.settings['username'],
                method_name=method_name,
                interface_object=obj
            )

            if i == len(interface_objects) - 1:
                save_session = True
            else:
                save_session = False

            self._store_data(
                key=key, data=crypto_block,
                save_session=save_session
            )

    def _set_crypto_for_object(
        self, crypto_block, method_name, interface_object
    ):

        key = self._get_crypto_object_key(
            username=self.settings['username'],
            method_name=method_name,
            interface_object=interface_object
        )

        self._store_data(
            key=key, data=crypto_block,
        )

    def _get_crypto_block_for_object(
        self, method_name, interface_object
    ):

        if not self.settings.get('username', False):
            self._start_session()

        key = self._get_crypto_object_key(
            username=self.settings['username'],
            method_name=method_name,
            interface_object=interface_object
        )

        return self._retrieve_data(key)

    def _internal_settings(self):
        return {
            'session': self._session,
            '_core_api': self._core_api,
            '_settings': self.settings,
            '_session_store': self._session_store,
        }

    def __getstate__(self):

        d = self.__dict__.copy()
        d['_session'] = None
        d['_core_api'] = None
        d['settings'] = self._get_settings()
        d['_session_store'] = {}

        return d


class Seat(object):
    """Represents a Seat in TSW, used in several other objects.

    The constructor is for internal user only.
    """

    def __init__(
        self,
        core_seat
    ):
        self._core_seat = core_seat

    @property
    def seat_id(self):
        return self._core_seat.full_id

    @property
    def is_restricted_view(self):
        """Boolean representing whether the seat has a restricted view."""
        return resolve_boolean(self._core_seat.is_restricted_view)

    @property
    def seat_text(self):
        """Additional information about this seat.

        E.g. restricted legroom
        """
        return self._core_seat.seat_text

    @property
    def column_id(self):
        return self._core_seat.col_id

    @property
    def row_id(self):
        return self._core_seat.row_id

    @property
    def column_sort_id(self):
        col = self._core_seat.col_id

        try:
            col = int(col)
        except ValueError:
            pass

        return col

    @property
    def row_sort_id(self):
        row = self._core_seat.row_id

        try:
            row = int(row)
        except ValueError:
            pass

        return row


class Customer(object):
    """Object that represents a customer.

    The 'core_customer' argument in the constructor is for internal use.

    The user, supplier and world can_use_data arguments are for data
    protection purposes and control who can use the customer's data.
    User is the TSW affiliate, supplier is the backend ticket supplier and
    world is third parties.

    Args:
        first_name (string): First name.
        last_name (string): Last name.
        home_phone (string): Home phone number.
        work_phone (string): Work phone number.
        address (Address): Home address.
        title (string): Optional, title.
        email_address (string): Optional, email address.
        user_can_use_data (boolean): Optional, data protection flag.
        supplier_can_use_data (boolean): Optional, data protection flag.
        world_can_use_data (boolean): Optional, data protection flag.
    """

    def __init__(
        self,
        core_customer=None,
        first_name=None,
        last_name=None,
        home_phone=None,
        work_phone=None,
        address=None,
        title=None,
        email_address=None,
        user_can_use_data=None,
        supplier_can_use_data=None,
        world_can_use_data=None
    ):

        self._core_customer = core_customer
        self._first_name = first_name
        self._last_name = last_name
        self._home_phone = home_phone
        self._work_phone = work_phone
        self._address = address
        self._title = title
        self._email_address = email_address
        self._user_can_use_data = user_can_use_data
        self._supplier_can_use_data = supplier_can_use_data
        self._world_can_use_data = world_can_use_data

    def _get_dict(self):
        return {
            'first_name': self.first_name,
            'last_name': self.last_name,
            'home_phone': self.home_phone,
            'work_phone': self.work_phone,
            'title': self.title,
            'email_address': self.email_address,
            'country_code': self.country_code,
            'address_line_one': self.address_line_one,
            'address_line_two': self.address_line_two,
            'town': self.town,
            'county': self.county,
            'postcode': self.postcode,
            'user_can_use_data': self.user_can_use_data,
            'supplier_can_use_data': self.supplier_can_use_data,
            'world_can_use_data': self.world_can_use_data,
        }

    @property
    def first_name(self):
        if self._core_customer:
            return self._core_customer.first_name
        else:
            return self._first_name

    @property
    def last_name(self):
        if self._core_customer:
            return self._core_customer.last_name
        else:
            return self._last_name

    @property
    def home_phone(self):
        if self._core_customer:
            return self._core_customer.home_phone
        else:
            return self._home_phone

    @property
    def work_phone(self):
        if self._core_customer:
            return self._core_customer.work_phone
        else:
            return self._work_phone

    @property
    def country_code(self):
        if self._core_customer:
            return self._core_customer.country_code
        else:
            return self._address.country_code

    @property
    def address_line_one(self):
        if self._core_customer:
            return self._core_customer.addr_line_one
        else:
            return self._address.address_line_one

    @property
    def address_line_two(self):
        if self._core_customer:
            return self._core_customer.addr_line_two
        else:
            return self._address.address_line_two

    @property
    def town(self):
        if self._core_customer:
            return self._core_customer.town
        else:
            return self._address.town

    @property
    def county(self):
        if self._core_customer:
            return self._core_customer.county
        else:
            return self._address.county

    @property
    def postcode(self):
        if self._core_customer:
            return self._core_customer.postcode
        else:
            return self._address.postcode

    @property
    def country(self):
        if self._core_customer:
            return self._core_customer.country
        else:
            return self._country

    @property
    def title(self):
        if self._core_customer:
            return self._core_customer.title
        else:
            return self._title

    @property
    def email_address(self):
        if self._core_customer:
            return self._core_customer.email_addr
        else:
            return self._email_address

    @property
    def user_can_use_data(self):
        if self._core_customer:
            return resolve_boolean(
                self._core_customer.dp_user
            )
        else:
            if isinstance(self._user_can_use_data, bool):
                return self._user_can_use_data
            elif isinstance(self._user_can_use_data, basestring):
                return resolve_boolean(
                    self._user_can_use_data
                )

    @property
    def supplier_can_use_data(self):
        if self._core_customer:
            return resolve_boolean(
                self._core_customer.dp_supplier
            )
        else:
            if isinstance(self._supplier_can_use_data, bool):
                return self._supplier_can_use_data
            elif isinstance(self._supplier_can_use_data, basestring):
                return resolve_boolean(
                    self._supplier_can_use_data
                )

    @property
    def world_can_use_data(self):
        if self._core_customer:
            return resolve_boolean(
                self._core_customer.dp_world
            )
        else:
            if isinstance(self._world_can_use_data, bool):
                return self._world_can_use_data
            elif isinstance(self._world_can_use_data, basestring):
                return resolve_boolean(
                    self._world_can_use_data
                )


class Card(object):
    """Object that represents a payment card.

    Args:
        card_number (string): The main card number.
        expiry_date (datetime.date): Expiry date of the card.
        cv_two (string): The card verification number (a.k.a CVV).
        start_date (datetime.date): Optional, start date of card.
        issue_number (string): Optional, card issue number.
        billing_address (Address): Optional, alternative billing address.
    """

    def __init__(
        self,
        card_number,
        expiry_date,
        cv_two,
        start_date=None,
        issue_number=None,
        billing_address=None
    ):

        self._card_number = card_number
        self._start_date = start_date
        self._expiry_date = expiry_date
        self._cv_two = cv_two
        self._issue_number = issue_number
        self._billing_address = billing_address

    def _get_dict(self):
        return {
            'card_number': self.card_number,
            'start_date': self.start_date_mmyy,
            'expiry_date': self.expiry_date_mmyy,
            'cv_two': self.cv_two,
            'issue_number': self.issue_number,
            'billing_address_line_one': self.billing_address_line_one,
            'billing_address_line_two': self.billing_address_line_two,
            'billing_town': self.billing_town,
            'billing_county': self.billing_county,
            'billing_postcode': self.billing_postcode,
            'billing_country_code': self.billing_country_code
        }

    @property
    def card_number(self):
        return self._card_number

    @property
    def start_date(self):
        return self._start_date

    @property
    def start_date_mmyy(self):
        """Returns string value in mmyy format"""
        if self.start_date:
            return self.start_date.strftime('%m%y')
        else:
            return None

    @property
    def expiry_date(self):
        return self._expiry_date

    @property
    def expiry_date_mmyy(self):
        """Returns string value in mmyy format"""
        return self.expiry_date.strftime('%m%y')

    @property
    def cv_two(self):
        return self._cv_two

    @property
    def issue_number(self):
        return self._issue_number

    @property
    def billing_address_line_one(self):
        if self._billing_address:
            return self._billing_address.address_line_one
        else:
            return None

    @property
    def billing_address_line_two(self):
        if self._billing_address:
            return self._billing_address.address_line_two
        else:
            return None

    @property
    def billing_town(self):
        if self._billing_address:
            return self._billing_address.town
        else:
            return None

    @property
    def billing_county(self):
        if self._billing_address:
            return self._billing_address.county
        else:
            return None

    @property
    def billing_postcode(self):
        if self._billing_address:
            return self._billing_address.postcode
        else:
            return None

    @property
    def billing_country_code(self):
        if self._billing_address:
            return self._billing_address.country_code
        else:
            return None


class Address(object):
    """Object that represents an address.

    The attributes are the same as the constructor arguments.

    Args:
        address_line_one (string): 1st line of address.
        country_code (string): 2 digit ISO 3166 country code.
        address_line_two (string): Optional, 2nd line of address.
        town (string): Optional, town.
        county (string): Optional, county.
        postcode (string): Optional, postcode.
    """

    def __init__(
        self,
        address_line_one,
        country_code,
        address_line_two=None,
        town=None,
        county=None,
        postcode=None
    ):

        self.address_line_one = address_line_one
        self.address_line_two = address_line_two
        self.town = town
        self.county = county
        self.postcode = postcode
        self.country_code = country_code


class CostRangeMixin(object):
    """Object to provide common cost range related functionality."""

    def _get_core_cost_range(self):
        """ This method must be overridden and should return a core
            cost range object.
        """
        raise NotImplementedError(
            'Subclasses must override _get_core_cost_range()'
        )

    @property
    def currency(self):
        """Returns a currency object."""
        currency = None
        cost_range = self._get_core_cost_range()

        if cost_range:
            currency = cost_range.currency

        return currency

    @property
    def min_seatprice(self):
        """Formatted string value of the minimun seat price with
        currency symbol.
        """
        min_price = None
        cost_range = self._get_core_cost_range()

        if cost_range:

            min_price = format_price_with_symbol(
                cost_range.min_seatprice,
                cost_range.currency.currency_pre_symbol,
                cost_range.currency.currency_post_symbol
            )

        return min_price

    @property
    def min_seatprice_float(self):
        """Float value of the minumum seat price."""
        fl_sp = None

        cost_range = self._get_core_cost_range()

        if cost_range:
            fl_sp = to_float_or_none(
                cost_range.min_seatprice
            )
        return fl_sp

    @property
    def min_combined_price(self):
        """Formatted string value of the minimun combined price with
        currency symbol.
        """
        min_price = None
        cost_range = self._get_core_cost_range()

        if cost_range:

            min_price = format_price_with_symbol(
                cost_range.min_combined,
                cost_range.currency.currency_pre_symbol,
                cost_range.currency.currency_post_symbol
            )

        return min_price

    @property
    def min_combined_price_float(self):
        """Float value of the minumum combined price."""
        fl_sp = None

        cost_range = self._get_core_cost_range()

        if cost_range:
            fl_sp = to_float_or_none(
                cost_range.min_combined
            )
        return fl_sp

    @property
    def max_combined_price_float(self):
        """Float value of the maximum combined price."""
        fl_sp = None

        cost_range = self._get_core_cost_range()

        if cost_range:
            fl_sp = to_float_or_none(
                cost_range.max_combined
            )
        return fl_sp

    @property
    def is_special_offer(self):
        """Boolean indicating if the object has a special offer."""
        cost_range = self._get_core_cost_range()

        if cost_range:
            if (
                cost_range.best_value_offer or
                cost_range.top_price_offer or
                cost_range.max_saving_offer
            ):
                return True

        return False

    @property
    def max_saving_percent(self):
        """Formatted string value of the maximum saving percentage
        with a '%' symbol.
        """
        cost_range = self._get_core_cost_range()
        per_sav = None

        if cost_range:
            if cost_range.best_value_offer:
                per_sav = '{0}%'.format(
                    cost_range.best_value_offer['percentage_saving']
                )

        return per_sav

    @property
    def max_saving_absolute(self):
        """Formatted string value of the maximum possible saving with
        currency symbol.
        """
        cost_range = self._get_core_cost_range()
        ab_sav = None

        if cost_range:
            if cost_range.max_saving_offer:
                ab_sav = format_price_with_symbol(
                    cost_range.max_saving_offer['absolute_saving'],
                    cost_range.currency.currency_pre_symbol,
                    cost_range.currency.currency_post_symbol
                )

        return ab_sav

    @property
    def best_value_non_offer_combined_price(self):
        """Formatted string value of the original cost of the best value
        offer price with currency symbol (i.e. if there was no offer)."""
        price = None
        cost_range = self._get_core_cost_range()

        if cost_range:
            if cost_range.best_value_offer:
                price = format_price_with_symbol(
                    cost_range.best_value_offer['full_combined'],
                    cost_range.currency.currency_pre_symbol,
                    cost_range.currency.currency_post_symbol
                )

        return price

    @property
    def best_value_offer_combined_price(self):
        """Formatted string value of the best value offer price with
        currency symbol."""
        price = None
        cost_range = self._get_core_cost_range()

        if cost_range:
            if cost_range.best_value_offer:
                price = format_price_with_symbol(
                    cost_range.best_value_offer['offer_combined'],
                    cost_range.currency.currency_pre_symbol,
                    cost_range.currency.currency_post_symbol
                )

        return price