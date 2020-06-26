import requests

class TelegramBot:
	def __init__(self,logger,settings):
		self.token= settings.token
		self.logChatId= settings.logChatId
		self.signalChannel= settings.signalChannel
		self.logger= logger

	def send_log(self,log_message):
		if self.logChatId is None:
			self.logger.warn("missing telegram logChatId")
			return
		self.__internal_send(self.logChatId,log_message)

	def send_signal(self,signal_message):
		if self.signalChannel is not None:
			self.__internal_send(self.signalChannel,signal_message)

	def __internal_send(self,chat_id,message):
		if self.token is None:
			self.logger.warn("missing telegram token or chatId")
			return

		url = 'https://api.telegram.org/bot' + self.token + '/sendMessage?chat_id=' + chat_id+ '&text=' + message

		result= requests.get(url).json()
		if not result["ok"]:
			self.logger.warning("error sending telegram messages "+str(result))
	